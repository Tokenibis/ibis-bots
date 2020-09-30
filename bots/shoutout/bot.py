import os
import json

from ibots import utils
from ibots.base import AbstractBasicBot

ACTIVITY_DESCRIPTION = '''Witnessed a random act of kindness? Want to spotlight your bff's
latest feat of awesomeness? Tell the world about it here!

Just reply _directly_ to this activity and mention the recipient
using Token Ibis's mention feature, something like:

> Hey @{username}, great job shouting people out.

{name} will send the recipient {amount} as a reward until funds run
out.

### Rules

* Shoutouts are for humans only
* You can't shout-out the same person twice in a month
* Funds aren't infinite, so the earlier the better
'''


class ShoutoutBot(AbstractBasicBot):
    def run(self, reward_amount):
        # retrieve the latest activity or create a new one if needed
        try:
            activity = self.activity_list(
                user=self.id,
                active=True,
                first=1,
            )[0]
        except (IndexError, ValueError):
            activity = self._new_activity(reward_amount)

        # retrieve the latest list of rewards
        rewards = self.reward_list(
            user=self.id,
            related_activity=activity['id'],
        )

        while True:
            comments = self.comment_list(parent=activity['id'])

            for comment in comments:
                mentions = self.person_list(mention_in=comment['id'])
                for target in mentions:
                    # only give rewards to human recipients that have
                    # not already received one from the same sender
                    if json.dumps([
                            comment['user']['id'],
                            target['id'],
                    ]) not in [x['scratch'] for x in rewards]:
                        # create the reward for the sender
                        reward = self.reward_create(
                            target=target['id'],
                            amount=reward_amount,
                            description=
                            'Hey {}, Here\'s a fresh shoutout from {}:\n\n{}'.
                            format(
                                target['first_name'],
                                comment['user']['first_name'],
                                self._clean_shoutout(
                                    comment['description'],
                                    mentions,
                                ),
                            ),
                            related_activity=activity['id'],
                            scratch=json.dumps([
                                comment['user']['id'],
                                target['id'],
                            ]))

                        # comment on the shoutout to link the reward
                        self.comment_create(
                            parent=comment['id'],
                            description=
                            'Thanks, here is a little [something]({}) for {}.'.
                            format(
                                self.get_app_link(reward['id']),
                                target['first_name'],
                            ))

                        # update the reward list
                        rewards = self.reward_list(
                            user=self.id,
                            related_activity=activity['id'],
                        )

            # if the activity is closed, start a new one
            if utils.localtime(activity['created']).month != utils.localtime(
            ).month or utils.localtime(
                    activity['created']).year != utils.localtime().year:
                self.activity_update(id=activity['id'], active=False)
                activity = self._new_activity(reward_amount)

            self.api_wait()

    def _new_activity(self, reward_amount):
        activity = self.activity_create(
            title='{} Shoutouts'.format(utils.localtime().strftime('%B')),
            description=ACTIVITY_DESCRIPTION.format(
                username=self.node['username'],
                name=self.node['name'],
                amount=utils.amount_to_string(reward_amount),
            ),
            active=True,
            reward_min=reward_amount,
        )
        return activity

    def _clean_shoutout(self, text, mentions):
        for x in mentions:
            text = text.replace(
                '@{}'.format(x['username']),
                x['first_name'],
            )
        return '> ' + '> \n'.join(text.split('\n'))
