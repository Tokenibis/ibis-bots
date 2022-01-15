import os
import datetime

from ibots import utils
from ibots.base import AbstractBasicBot

ACTIVITY_TITLE = 'Refer Friends to Token Ibis'

ACTIVITY_DESCRIPTION = '''If you recommend a friend to Token Ibis using your personal
[invite link]({invite_link}), Referral Bot will send _both_ you and your
friend some bonus money. Ground rules:

* Only people (not organizations) can make referrals
* Both you and your friend have to __verify your phone numbers__ to
  qualify.

## Reward Amounts

Referral Bot will send you a reward for any friends that you directly
refer (Level 1), a smaller reward for anyone that your friend refers
(Level 2), and so on. It's basically a pyramid scheme, except that
Token Ibis pays for it and it helps people. #notascam

Here are the current reward amounts:

__New Referred Users__: {referred_amount}

__Referrers__: 

{referrer_amounts}

## Past Referrals

Here is the latest referral tree:

{pyramid}

---

_If you're not on this list, you probably need to verify your phone number.
The Token Ibis referral system is also in testing right now, so please
email __info@tokenibis.org__ if you feel there was any error with your
referrals. Token Ibis is not doing retroactive referrals at this
time._

'''

REWARD_DESCRIPTION_REFERRED = '''Hello {referred_name}, thanks for
letting @{referrer_username} refer
you to Token Ibis!

'''

REWARD_DESCRIPTION_DIRECT = '''Hello {referrer_name} thanks for
referring @{referred_username} to Token Ibis!

'''

REWARD_DESCRIPTION_INDIRECT = '''Hello {referrer_name},
congratulations! One of your referrals referred
[{referred_name}]({referred_link}) to Token Ibis!

'''

DIR = os.path.dirname(os.path.realpath(__file__))


class ReferralBot(AbstractBasicBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with open(os.path.join(DIR, 'query.gql')) as fd:
            self.register_custom_gql('ReferralBotPersonList', 'list',
                                     fd.read())

    def run(
            self,
            referrer_amounts,
            referred_amount,
    ):

        # retrieve the latest activity or create a new one if needed
        try:
            activity = self.activity_list(
                user=self.id,
                active=True,
                first=1,
            )[0]
        except (IndexError, ValueError):
            activity = self.activity_create(
                title=ACTIVITY_TITLE,
                description='',
                active=True,
                scratch='{}',
            )

        while True:

            people = self.call_custom_gql(
                'ReferralBotPersonList',
                verified=True,
                order_by='date_joined',
            )

            id_lookup = {x['id']: x for x in people}

            # calculate the pyramid structure of the pyramid referral scheme
            referrals = {
                x['id']:
                [y for y in id_lookup if id_lookup[y]['referral'] == x['id']]
                for x in people
            }

            def _make_pyramid(nodes, refs, seen=set()):
                tree = []
                for node in nodes:
                    if node in seen:
                        continue
                    seen.add(node)
                    subtree = _make_pyramid(refs[node], refs, seen)
                    tree.append({'id': node, 'children': subtree})

                return tree

            pyramid = _make_pyramid([x['id'] for x in people], referrals)

            def _serialize_pyramid(children, depth=1):
                return ''.join([
                    '{} @{}\n\n{}'.format(
                        'o &nbsp;&nbsp;&nbsp;&nbsp;' * depth,
                        id_lookup[x['id']]['username'],
                        _serialize_pyramid(x['children'], depth=depth + 1),
                    ) for x in children
                ])

            # update the activity to show the latest pyramid structure
            activity = self.activity_update(
                id=activity['id'],
                title=ACTIVITY_TITLE,
                description=ACTIVITY_DESCRIPTION.format(
                    invite_link='https://{}/#/Person/PersonList'.format(
                        self._endpoint.split('.', 1)[1]),
                    referred_amount='${:.2f}'.format(referred_amount / 100),
                    referrer_amounts='\n'.join(
                        '* __Level {}__: ${:.2f}'.format(i + 1, x / 100)
                        for i, x in enumerate(referrer_amounts)),
                    pyramid=_serialize_pyramid(pyramid)),
                reward_min=min([referred_amount] + referrer_amounts),
                reward_range=max([referred_amount] + referrer_amounts) -
                min([referred_amount] + referrer_amounts),
            )

            # make unpaid payouts according the pyramid structure
            identifier_set = set(
                x['scratch']
                for x in self.reward_list(user=self.id, order_by='created'))

            def _get_ancestor_pairs(children, ancestors=[]):
                """returns a list of all combinations of (node,
                ancestor, depth) tuples """
                return [
                    x for c in children
                    for x in [(a, c['id'], d)
                              for a, d in ancestors] + _get_ancestor_pairs(
                                  c['children'],
                                  [(a2, d2 + 1)
                                   for a2, d2 in ancestors] + [(c['id'], 1)],
                              )
                ]

            for ancestor, node, depth in _get_ancestor_pairs(pyramid):
                if not id_lookup[node]['verified_original']:
                    continue
                if depth <= len(referrer_amounts) and 'referrer:{}:{}'.format(
                        ancestor,
                        node,
                ) not in identifier_set:
                    self.reward_create(
                        target=ancestor,
                        amount=referrer_amounts[depth - 1],
                        description=REWARD_DESCRIPTION_DIRECT.format(
                            referrer_name=id_lookup[ancestor]['first_name'],
                            referred_username=id_lookup[node]['username'],
                        )
                        if depth == 1 else REWARD_DESCRIPTION_INDIRECT.format(
                            referrer_name=id_lookup[ancestor]['first_name'],
                            referred_name=id_lookup[node]['name'],
                            referred_link=self.get_app_link(
                                id_lookup[node]['id']),
                        ),
                        scratch='referrer:{}:{}'.format(ancestor, node),
                    )
                if depth == 1 and 'referred:{}:{}'.format(
                        ancestor,
                        node,
                ) not in identifier_set:
                    self.reward_create(
                        target=node,
                        amount=referred_amount,
                        description=REWARD_DESCRIPTION_REFERRED.format(
                            referred_name=id_lookup[node]['first_name'],
                            referrer_username=id_lookup[ancestor]['username']),
                        scratch='referred:{}:{}'.format(ancestor, node),
                    )

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
