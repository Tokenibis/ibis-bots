import os
import sys
import json
import spacy
import random
import datetime
import subprocess

from ibots import utils
from ibots.base import AbstractBasicBot

DIR = os.path.dirname(os.path.realpath(__file__))

nlp = spacy.load('en')

TOP_K = 40

START_CONTEXT = 'Once upon a time,'

INTRO_TITLE = 'One Thousand and One Bytes: Introduction'

INTRO_DESCRIPTION = '''One Thousand and One Bytes is a collaborative story between human and
machine. Users submit new entries to the story everyday. At midnight,
Story Bot will add the highest-voted submission to the offical
publication. On days when there are no submissions, Story Bot will
write its own continuation of the story.

All Token Ibis users can make as many submissions as often as you
like, but only people (not organizations or bots) can earn rewards and
will only get paid once per _page_ (if your submission is selected).

The story starts with this post and it will continue for as long as
Token Ibis and Story Bot exists. Someday, it will probably be 100%
user-driven. Until then, Story Bot's machine learning algorithms will
here to stumble along, occasionally guide by a helpful human.

## Table of Contents

| Page &nbsp; &nbsp; &nbsp; | Published &nbsp; &nbsp; &nbsp; | Contributors &nbsp; &nbsp; &nbsp; |
|:-|:-|:-|
{pages}

'''

PAGE_TITLE = 'One Thousand and One Bytes: Page {}'

PAGE_DESCRIPTION = '''_This is page {page_number} of "One Thousand and One Bytes", a
collaborative work of fiction by human Token Ibis users and computer
algorithms. Please see the commnet section for instructions or visit
the [the table of contents]({intro_link}) to browse all pages._

---

{content}

---

{navigation}

'''

ROOT_DESCRIPTION = '''__INSTRUCTIONS.__ Story Bot publishes exactly one new entry to the
story everyday. To make your submission, please _comment_ to
the daily submission slot below. Submissions close at midnight MT.
Story Bot selects winners based on the most number of _likes_
(tie-breakers are random). If there are no user submissions, Story Bot
will machine-generate a new entry and move on to the next day.'''

SLOT_DESCRIPTION = '__{} SUBMISSIONS.__ Reply _directly_ to this comment make a submission for today\'s entry.'

CLOSE_DESCRIPTION = '__CLOSED.__ Submissions are closed for this day. Please check back soon for tomorrow\'s entry.'

REWARD_DESCRIPTION = '''Thank you for your contribution to _One Thousand and One Bytes_!
Story Bot believes that good stories can bring people (and bots)
together.'''


class StoryBot(AbstractBasicBot):
    def run(
            self,
            model,
            reward_amount,
            context_length,
            text_length,
            page_length,
    ):
        self.model = model
        self.text_length = text_length

        # retrieve the table of contents activity or create new one
        try:
            intro = self.activity_list(
                user=self.id,
                active=False,
                first=1,
                order_by='created',
            )[0]
        except (IndexError, ValueError):
            intro = self.activity_create(
                title=INTRO_TITLE,
                description='Generating initial story...',
                reward_min=0,
                active=False,
                scratch=json.dumps({
                    'type': 'toc',
                    'pages': []
                }),
            )

        intro_link = self.get_app_link(intro['id'])

        # retrieve the latest page activity or create a new one if needed
        try:
            page = list(
                reversed(
                    self.activity_list(
                        user=self.id,
                        order_by='-created',
                        first=2,
                    )))[1]
            bootstrapping = False
        except (IndexError, ValueError):
            page = self.activity_create(
                title=PAGE_TITLE.format(1),
                description='Generating initial story...',
                active=True,
                reward_min=reward_amount,
                scratch=json.dumps({
                    'type': 'page',
                    'number': 1,
                    'intro_link': intro_link,
                    'prev_link': '',
                    'next_link': '',
                    'entries': [],
                }))
            bootstrapping = True

        while True:
            now = utils.localtime()
            page, root, slots = self.initiate_page(
                now,
                page,
                bootstrapping=bootstrapping,
            )

            # if deadline for last slot has passed
            if bootstrapping or utils.localtime(
                    slots[-1]['created']).day != now.day:

                # if we haven't closed, then make sure to close
                if not self.comment_list(
                        parent=slots[-1]['id'],
                        user=self.id,
                        first=1,
                ):
                    self.comment_create(
                        parent=slots[-1]['id'],
                        description=CLOSE_DESCRIPTION,
                    )

                scratch = json.loads(page['scratch'])

                # if we haven't a chosen winner, then choose a winner
                if len(scratch['entries']) < len(slots):
                    submissions = [
                        x for x in self.comment_list(parent=slots[-1]['id'])
                        if x['user']['id'] != self.id
                    ]
                    if submissions:  # choose user submission
                        submissions.sort(key=lambda x: (
                            x['like_count'],
                            random.random(),
                        ))
                        user = submissions[-1]['user']
                        text = submissions[-1]['description']
                    else:  # use gpt2 to generate next entry
                        user = slots[-1]['user']

                        if bootstrapping:
                            context = START_CONTEXT
                        else:
                            # construct context from previous entries
                            context_list = []
                            current_page = page
                            current_scratch = json.loads(page['scratch'])
                            entry_number = len(current_scratch['entries']) - 1

                            while len(context_list) < context_length:
                                if entry_number < 0:
                                    current_page = self.activity_list(
                                        user=self.id,
                                        order_by='-created',
                                        created_before=current_page['created'],
                                        first=1,
                                    )[0]

                                    current_scratch = json.loads(
                                        current_page['scratch'])
                                    if not current_scratch['type'] == 'page':
                                        self.logger.info('Incomplete context.')
                                        break

                                    entry_number = len(current_scratch) - 1

                                context_list = list(
                                    nlp(current_scratch['entries']
                                        [entry_number]['text'] +
                                        '\n\n')) + context_list

                                entry_number -= 1

                            context = ''.join(
                                x.text_with_ws
                                for x in context_list[len(context_list) -
                                                      context_length:])

                        self.logger.debug('Starting gpt2 generation')

                        # call gpt2 using context and other parameters
                        while True:
                            try:
                                gpt2_text = subprocess.check_output([
                                    sys.executable,
                                    os.path.join(
                                        DIR,
                                        'gpt2',
                                        'generate_text.py',
                                    ),
                                    context,
                                    '--length',
                                    str(text_length),
                                    '--top_k',
                                    str(TOP_K),
                                    '--model_name',
                                    self.model,
                                ]).decode('utf-8').replace(
                                    '<|endoftext|>', ' ').strip()
                                break
                            except subprocess.CalledProcessError:
                                self.logger.info(
                                    'GPT-2 memory error; trying again with smaller context'
                                )
                                context = ' '.join(
                                    context.split(' ')
                                    [int(context.count(' ') / 4):])
                                continue

                        self.logger.debug('Done with gpt2 generation')

                        # use spacy to trim off dangling sentence
                        text = ''.join(
                            x.text_with_ws
                            for x in list(nlp(gpt2_text).sents)[:-1]).strip()

                        if bootstrapping:
                            text = START_CONTEXT + ' ' + text

                    scratch['entries'].append({
                        'user': user,
                        'text': text,
                    })

                    page = self.update_page(page, scratch)

                    if bootstrapping:
                        bootstrapping = False

                intro = self.update_intro(intro, page)

                # send out reward
                if scratch['entries'][-1]['user'][
                        'user_type'] == 'person' and scratch['entries'][-1][
                            'user']['id'] not in [
                                x['target']['id'] for x in self.reward_list(
                                    user=self.id,
                                    related_activity=page['id'],
                                )
                            ]:
                    self.reward_create(
                        target=scratch['entries'][-1]['user']['id'],
                        amount=reward_amount,
                        description=REWARD_DESCRIPTION,
                        related_activity=page['id'],
                    )

                # create new submission or new page
                if len(slots) < page_length:
                    self.comment_create(
                        parent=root['id'],
                        description=SLOT_DESCRIPTION.format(
                            now.strftime('%B %d, %Y')),
                    )
                else:
                    page = self.activity_update(id=page['id'], active=False)
                    page = self.activity_create(
                        title=PAGE_TITLE.format(scratch['number'] + 1),
                        description='Generating initial story...',
                        active=True,
                        reward_min=reward_amount,
                        scratch=json.dumps({
                            'type':
                            'page',
                            'number':
                            scratch['number'] + 1,
                            'entries': [],
                            'intro_link':
                            intro_link,
                            'prev_link':
                            self.get_app_link(page['id']),
                            'next_link':
                            '',
                        }))
                    page, root, slots = self.initiate_page(
                        utils.localtime(),
                        page,
                    )
                    intro = self.update_intro(intro, page)

            # wait until midnight
            now = utils.localtime()
            self.api_wait(
                timeout=((
                    now.astimezone(datetime.timezone.utc) +
                    datetime.timedelta(days=1)).astimezone(now.tzinfo).replace(
                        hour=0,
                        minute=0,
                        second=0,
                    ) - now).total_seconds())

    def initiate_page(self, now, page, bootstrapping=False):
        scratch = json.loads(page['scratch'])
        if scratch['number'] > 1:
            previous = self.activity_list(
                user=self.id,
                created_before=page['created'],
                order_by='-created',
                first=1,
            )[0]
            prev_scratch = json.loads(previous['scratch'])
            prev_scratch['next_link'] = self.get_app_link(page['id'])
            self.update_page(previous, prev_scratch)

        try:
            root = self.comment_list(
                parent=page['id'], user=self.id, first=1)[0]
        except IndexError:
            root = self.comment_create(
                parent=page['id'],
                description=ROOT_DESCRIPTION,
            )

        # create first submission slot if we haven't already
        slots = self.comment_list(
            parent=root['id'],
            user=self.id,
            order_by='created',
        )
        if not slots:
            slots = [
                self.comment_create(
                    parent=root['id'],
                    description='__INITIAL ENTRY__' if bootstrapping else
                    SLOT_DESCRIPTION.format(now.strftime('%B %d, %Y')),
                )
            ]

        return self.update_page(page, scratch), root, slots

    def update_page(self, page, scratch):
        navigation = '__Page {}__ | [table of contents]({})'.format(
            scratch['number'],
            scratch['intro_link'],
        )
        if scratch['prev_link'] and scratch['next_link']:
            navigation += ' | [prev]({}) | [next]({})'.format(
                scratch['prev_link'],
                scratch['next_link'],
            )
        elif scratch['prev_link']:
            navigation += ' | [prev]({})'.format(scratch['prev_link'])
        elif scratch['next_link']:
            navigation += ' | [next]({})'.format(scratch['next_link'])

        return self.activity_update(
            id=page['id'],
            title=PAGE_TITLE.format(scratch['number']),
            description=PAGE_DESCRIPTION.format(
                page_number=scratch['number'],
                intro_link=scratch['intro_link'],
                content='\n\n'.join('{} (@{})'.format(
                    x['text'],
                    x['user']['username'],
                ) for x in scratch['entries']) if scratch['entries'] else
                '_[Previously]({}) on One Thousand and One Bytes..._'.format(
                    scratch['prev_link']),
                navigation=navigation,
            ),
            scratch=json.dumps(scratch),
        )

    def update_intro(self, intro, page):
        scratch = json.loads(page['scratch'])
        intro_scratch = json.loads(intro['scratch'])
        page_info = {
            'link': self.get_app_link(page['id']),
            'created': page['created'],
            'contributors': [x['user'] for x in scratch['entries']],
        }
        if scratch['number'] > len(intro_scratch['pages']):
            intro_scratch['pages'].append(page_info)
        else:
            intro_scratch['pages'][scratch['number'] - 1] = page_info
        return self.activity_update(
            id=intro['id'],
            title=INTRO_TITLE,
            description=INTRO_DESCRIPTION.format(pages='\n'.join(
                '| [{}]({}) | {} | {} |'.format(
                    i + 1,
                    x['link'],
                    utils.localtime(x['created']).strftime('%m.%d.%y'),
                    ', '.join(
                        sorted(
                            set(y['first_name'] for y in x['contributors']))),
                ) for i, x in enumerate(intro_scratch['pages']))),
            scratch=json.dumps(intro_scratch),
        )
