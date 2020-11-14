import json
import spacy
import random

from nltk.corpus import words
from ibots import utils
from ibots.base import AbstractBasicBot

WORDS = set(words.words())

ACTIVITY_TITLE = 'Collective Vocabulary'

ACTIVITY_DESCRIPTION = '''Vocabulary Bot rewards users who make an impact using awesome
language skills. Every week (starting {weekday}), if you use a new
word that Vocabulary Bot has never seen before in a donation
description, you'll have a chance to earn a reward for your
[sesquipedalian](https://www.merriam-webster.com/dictionary/sesquipedalian)
prowess.

## Vocabulary Winners

{reward_recipients}

## Vocabulary Words

| Word | Count |
|:-----|:------|
{word_count}
'''

REWARD_DESCRIPTION = '''Hey {name}, thanks for adding to Token Ibis\'s vocabulary by being
the first to use the word: [{word}]({link}).

'''

nlp = spacy.load('en')


class VocabularyBot(AbstractBasicBot):
    def run(self, reward_amount, weekday, recalculate):
        self.reward_amount = reward_amount
        self.weekday = weekday

        # retrieve the latest activity or create a new one if needed
        try:
            activity = self.activity_list(
                user=self.id,
                active=True,
                first=1,
            )[0]
        except (IndexError, ValueError):
            activity = self.activity_create(
                title='',
                description='',
                active=True,
            )

        if recalculate or not activity['scratch']:
            if recalculate and activity['scratch']:
                epoch_start = utils.localtime(
                    json.loads(activity['scratch'])['epoch_start'])
            else:
                epoch_start = utils.epoch_start(
                    self.weekday,
                    utils.localtime(),
                )

            activity = self._update_activity(
                activity['id'], {
                    'epoch_start':
                    str(epoch_start),
                    'word_count':
                    self._word_count(x['description']
                                     for x in self.donation_list(
                                         created_before=str(epoch_start))),
                    'reward_recipients':
                    [{
                        'user_id': x['target']['id'],
                        'user_name': x['target']['name'],
                        'reward_id': x['id'],
                        'donation_id': json.loads(x['scratch'])['donation_id'],
                        'word': json.loads(x['scratch'])['word'],
                        'reward_created': x['created'],
                    } for x in self.reward_list(
                        user=self.id,
                        related_activity=activity['id'],
                    )],
                })

        scratch = json.loads(activity['scratch'])

        while True:
            epoch_start = utils.epoch_start(self.weekday, utils.localtime())

            # if we have moved on to a new epoch
            if epoch_start > utils.localtime(scratch['epoch_start']):

                # calculate word_counts of donations in the previous epoch
                word_counts = [(
                    x,
                    self._word_count([x['description']]),
                ) for x in self.donation_list(
                    created_after=str(scratch['epoch_start']),
                    created_before=str(epoch_start),
                )]

                # add new wordcounts and determine possible reward candidates
                reward_candidates = {}
                for donation, word_count in word_counts:
                    for word, count in word_count.items():
                        if word in scratch['word_count']:
                            scratch['word_count'][word] += word_count[word]
                        else:
                            scratch['word_count'][word] = word_count[word]
                            if donation['user']['id'] not in reward_candidates:
                                reward_candidates[donation['user']['id']] = []
                            reward_candidates[donation['user']['id']].append({
                                'user_id':
                                donation['user']['id'],
                                'user_name':
                                donation['user']['name'],
                                'donation_id':
                                donation['id'],
                                'word':
                                word,
                            })

                # send reward if we haven't already
                if reward_candidates and not self.reward_list(
                        user=self.id,
                        related_activity=activity['id'],
                        created_after=str(epoch_start),
                ):
                    winner = random.choice(
                        random.choice(list(reward_candidates.values())))
                    reward = self.reward_create(
                        target=winner['user_id'],
                        amount=reward_amount,
                        related_activity=activity['id'],
                        description=REWARD_DESCRIPTION.format(
                            name=winner['user_name'],
                            word=winner['word'],
                            link=self.get_app_link(winner['donation_id']),
                        ),
                        scratch=json.dumps({
                            'donation_id': winner['donation_id'],
                            'word': winner['word'],
                        }))
                    winner['reward_id'] = reward['id']
                    scratch['reward_recipients'].insert(0, winner)

                # update the activity
                scratch['epoch_start'] = str(epoch_start)
                activity = self._update_activity(activity['id'], scratch)
                scratch = json.loads(activity['scratch'])

            # wait until the start of the next epoch
            now = utils.localtime()
            self.api_wait(
                timeout=(utils.epoch_start(
                    self.weekday,
                    now,
                    offset=1,
                ) - now).total_seconds())

    def _update_activity(self, id, scratch):
        activity = self.activity_update(
            id=id,
            title=ACTIVITY_TITLE,
            description=ACTIVITY_DESCRIPTION.format(
                weekday=self.weekday,
                reward_recipients='\n'.join('* [{}]({}) — [{}]({})'.format(
                    x['user_name'],
                    self.get_app_link(x['user_id']),
                    x['word'],
                    self.get_app_link(x['reward_id']),
                ) for x in scratch['reward_recipients']),
                word_count='\n'.join(
                    '| {}&nbsp;&nbsp;&nbsp;&nbsp;| {} |'.format(
                        word,
                        count,
                    ) for word, count in sorted(
                        [x for x in scratch['word_count'].items()],
                        key=lambda x: x[1],
                        reverse=True,
                    )),
            ),
            scratch=json.dumps(scratch),
            reward_min=self.reward_amount,
        )
        return activity

    def _word_count(self, descriptions):
        count = {}
        for description in descriptions:
            doc = nlp(description)
            for token in doc:
                if token.is_alpha and not token.is_stop:
                    word = token.lemma_.lower()
                    if word in WORDS:
                        if word not in count:
                            count[word] = 0
                        count[word] += 1

        return count
