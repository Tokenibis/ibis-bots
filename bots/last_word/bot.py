import json
import requests

from datetime import timedelta
from ibots.base import AbstractBasicBot
from ibots import utils

'http://jservice.io/api/random'

ACTIVITY_TITLE = 'The Last Word: Round {}'

ACTIVITY_DESCRIPTION = '''Welcome to the latest edition of _The Last Word_. The game is
simple: reply to this activity (or any comment in this activity) as
many times as you would like. Whoever (humans only) submits the _last_
reply wins the pot of money if nobody responds within {countdown}
days. The more people participate and the longer it goes on, the
bigger the pot gets!

### The First Word

Here is something to get the discussion started:

> "{quote}"

_—{author}_

### The Last Word

> "{words}"

_—{leader}_

### Stats

* number of participants: {num_participants}
* reward amount: {reward}
* countdown to: {end}
'''


class LastWordBot(AbstractBasicBot):

    _time_format = '%B %d, %Y at %I:%M %p'

    def run(self, countdown_days, reward_min, reward_increment, reward_max):
        try:
            activity = self.activity_list(
                user=self.id,
                active=True,
                first=1,
            )[0]
            quote = json.loads(activity['scratch'])

        except (TypeError, IndexError, ValueError):
            activity = self._new_activity(
                reward_amount=reward_min,
                end=utils.localtime() + timedelta(days=countdown_days),
                countdown=countdown_days,
            )
            quote = json.loads(activity['scratch'])

        while True:

            comments = sorted(
                self._flatten(self.comment_tree(root=activity['id'])),
                key=lambda x: utils.localtime(x['created']),
            )

            if not comments:
                self.api_wait(timeout=3600 * 24 * countdown_days)
                continue

            num_participants = len(
                set(x['user']['id'] for x in comments
                    if x['user']['user_type'] == 'Person'))
            last_time = utils.localtime(comments[-1]['created'])
            reward_amount = min(
                reward_min + reward_increment * num_participants +
                reward_increment * round(
                    (last_time - utils.localtime(activity['created'])).days /
                    7),
                reward_max,
            )

            description = ACTIVITY_DESCRIPTION.format(
                leader=comments[-1]['user']['name'],
                words=comments[-1]['description'],
                num_participants=num_participants,
                quote=quote['quote'],
                author=quote['author'],
                reward=utils.amount_to_string(reward_amount),
                end=(last_time + timedelta(days=countdown_days)).strftime(
                    self._time_format),
                countdown=countdown_days,
            )

            if utils.localtime() < last_time + timedelta(days=countdown_days):
                self.activity_update(
                    id=activity['id'],
                    description=description,
                    reward_min=reward_amount,
                )

            else:
                reward = self.reward_create(
                    target=comments[-1]['user']['id'],
                    amount=reward_amount,
                    description='Truly one for the ages:\n\n> "{}" \n\n_—{}_'.
                    format(
                        comments[-1]['description'],
                        comments[-1]['user']['name'],
                    ),
                    related_activity=activity['id'],
                )

                self.activity_update(
                    id=activity['id'],
                    description='{}\n\n—\n\n{}'.format(
                        description,
                        'Congratulations, @{}. Here is your well-earned [reward]({})!'
                        .format(
                            comments[-1]['user']['username'],
                            self.get_app_link(reward['id']),
                        )),
                    reward_min=reward_amount,
                    active=False,
                )

                activity = self._new_activity(
                    reward_min,
                    utils.localtime() + timedelta(days=countdown_days),
                    countdown=countdown_days,
                )

            self.api_wait(timeout=3600 * 24 * countdown_days)

    def _new_activity(self, reward_amount, end, countdown):
        self.refresh_node()

        quote = requests.get('https://{}/ibis/quote/'.format(
            self._endpoint)).json()

        return self.activity_create(
            title=ACTIVITY_TITLE.format(self.node['activity_count']),
            description=ACTIVITY_DESCRIPTION.format(
                leader='Your Name Here',
                words='I wonder what I would do with {}?'.format(
                    utils.amount_to_string(reward_amount)),
                num_participants=0,
                quote=quote['quote'],
                author=quote['author'],
                reward=utils.amount_to_string(reward_amount),
                end=end.strftime(self._time_format),
                countdown=countdown,
            ),
            active=True,
            reward_min=reward_amount,
            scratch=json.dumps(quote),
        )

    def _flatten(self, obj):
        return [
            y for x in obj for y in self._flatten(x['replies_']) +
            [{z: x[z]
              for z in x if z != 'replies_'}]
        ]
