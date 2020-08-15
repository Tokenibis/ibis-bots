import random

from datetime import timedelta
from ibots.base import AbstractBasicBot
from ibots import utils

ACTIVITY_TITLE = 'Prisoner\'s Dilemma: Round {}'

ACTIVITY_DESCRIPTION = '''Ah, prisoner\'s dilemma—game theory\'s poster-child for
understanding nuclear deterence, evolution, and life—now available as
a low-budget knock-off on Token Ibis. Learn more
[here](https://en.wikipedia.org/wiki/Prisoner%27s_dilemma) puzzle.

### Scenario

You and another Token Ibis user have been arrested for the heist of
the century. The authorities, being fairly clever, decide to separate
the two of you to extract confessions. You have two options: keep your
mouth shut (__cooperate__ with your accomplice), or snitch
(__defect__). If you cooperate, both of you walk away unscathed. If
you snitch, then your partner takes the fall, and you walk away with
the prize all to yourself. But don't forget to consider the biggest
question: what will _they_ decide?

### Rules

* __Like__ one of {bot}'s comments below to __cooperate__ or __defect__
* If you __like__ both, {bot} will choose one randomly
* After enough people have decided, {bot} will choose two random players
* Depending on their decision, they will receive rewards according to
  the following matrix:

> |                            | Defect (You)   | Cooperate (You) |
> |----------------------------|----------------|-----------------|
> | __Defect (Accomplice)__    | {defect}       | {lose}          |
> | __Cooperate (Accomplice)__ | {win}          | {cooperate}     |

If chosen, your final decision will be posted. So choose wisely.

### Current Participants

{participants}
'''

ACTIVITY_CLOSE = '''
---

### Final Decisions

{conclusion}

@{player1}: __{choice1}__{random1}

@{player2}: __{choice2}__{random2}
'''

DESC_COOPERATE = 'Congratulations! Both of you held tight and are made out with the full prize.'
DESC_DEFECT = 'Both of you are worse of the wear. But hey, at least you\'re not a sucker.'
DESC_WIN = 'Nice job, you "won". It\'s a dog-eat-dog world.'
DESC_LOSE = 'Touch luck, you took honorable path and paid the price.'

CONCLUSION_COOPERATE = 'Both {name1} and {name2} held firm. Hooray for cooperation!'
CONCLUSION_DEFECT = '{name1} and {name2} both defected. There\'s no honor among thieves.'
CONCLUSION_MIXED = '{name1} chose to defect, and {name2} got screwed. Sucks to suck.'


class PrisonersDilemmaBot(AbstractBasicBot):
    def run(
            self,
            min_players,
            duration_hours,
            amount_cooperate,
            amount_defect,
            amount_win,
            amount_lose,
    ):

        start_description = ACTIVITY_DESCRIPTION.format(
            bot=self.node['name'],
            cooperate=utils.amount_to_string(amount_cooperate),
            defect=utils.amount_to_string(amount_defect),
            win=utils.amount_to_string(amount_win),
            lose=utils.amount_to_string(amount_lose),
            participants='_No one yet_',
        )

        assert min_players >= 2, 'Minimum 2 players'

        try:
            activity = self.activity_list(
                user=self.id,
                active=True,
                first=1,
            )[0]
        except (IndexError, ValueError):
            activity = self._new_activity(description)

        while True:
            cooperate, defect = self.comment_list(
                user=self.id,
                parent=activity['id'],
                order_by='created',
                first=2,
            )

            cooperators = {
                x['id']: x
                for x in self.person_list(like_for=cooperate['id'])
            }
            defectors = {
                x['id']: x
                for x in self.person_list(like_for=defect['id'])
            }

            players = {**cooperators, **defectors}

            description = ACTIVITY_DESCRIPTION.format(
                bot=self.node['name'],
                cooperate=utils.amount_to_string(amount_cooperate),
                defect=utils.amount_to_string(amount_defect),
                win=utils.amount_to_string(amount_win),
                lose=utils.amount_to_string(amount_lose),
                participants='{}{}'.format(
                    '* ',
                    '\n* '.join(players[x]['name'] for x in players),
                ) if players else '_No one yet_',
            ) if players else start_description

            # if the activity is closed, calculate earning and send rewards
            if not (len(players) >= min_players and
                    utils.localtime() > utils.localtime(activity['created']) +
                    timedelta(hours=duration_hours)):
                self.activity_update(
                    id=activity['id'],
                    description=description,
                )
            else:
                p1, p2 = random.sample(list(players.values()), 2)

                for x in [p1, p2]:
                    if x['id'] in cooperators and x['id'] in defectors:
                        x['_cooperate'] = random.random() < 0.5
                        x['_random'] = True
                    elif x['id'] in cooperators:
                        x['_cooperate'] = True
                        x['_random'] = False
                    elif x['id'] in defectors:
                        x['_cooperate'] = False
                        x['_random'] = False
                    else:
                        self.logger.error('Logical error in the decision code')
                        raise ValueError

                if p1['_cooperate'] and p2['_cooperate']:
                    p1['_amount'] = p2['_amount'] = amount_cooperate
                    p1['_desc'] = p2['_desc'] = DESC_COOPERATE
                    conclusion = CONCLUSION_COOPERATE.format(
                        name1=p1['name'],
                        name2=p2['name'],
                    )
                elif p1['_cooperate'] and not p2['_cooperate']:
                    p1['_amount'], p2['_amount'] = amount_lose, amount_win
                    p1['_desc'], p2['_desc'] = DESC_LOSE, DESC_WIN
                    conclusion = CONCLUSION_MIXED.format(
                        name1=p1['name'],
                        name2=p2['name'],
                    )
                elif not p1['_cooperate'] and p2['_cooperate']:
                    p1['_amount'], p2['_amount'] = amount_win, amount_lose
                    p1['_desc'], p2['_desc'] = DESC_WIN, DESC_LOSE
                    conclusion = CONCLUSION_MIXED.format(
                        name1=p1['name'],
                        name2=p2['name'],
                    )
                else:
                    p1['_amount'] = p2['_amount'] = amount_defect
                    p1['_desc'] = p2['_desc'] = DESC_LOSE
                    conclusion = CONCLUSION_DEFECT.format(
                        name1=p1['name'],
                        name2=p2['name'],
                    )

                for x in [p1, p2]:
                    self.reward_create(
                        target=x['id'],
                        amount=x['_amount'],
                        description=x['_desc'],
                        related_activity=activity['id'],
                    )

                self.activity_update(
                    id=activity['id'],
                    active=False,
                    description=description + ACTIVITY_CLOSE.format(
                        player1=p1['username'],
                        player2=p2['username'],
                        choice1='cooperate' if p1['_cooperate'] else 'defect',
                        choice2='cooperate' if p2['_cooperate'] else 'defect',
                        random1=' (random)' if p1['_random'] else '',
                        random2=' (random)' if p2['_random'] else '',
                        conclusion=conclusion,
                    ),
                )

                activity = self._new_activity(start_description)

            self.api_wait()

    def _new_activity(self, description):

        activity = self.activity_create(
            title=ACTIVITY_TITLE.format(self.node['activity_count']),
            description=description,
            active=True,
            reward_min=1,
            reward_range=2000 - 1,
        )
        self.comment_create(parent=activity['id'], description='__DEFECT__')
        self.comment_create(parent=activity['id'], description='__COOPERATE__')

        return activity
