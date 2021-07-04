import os
import json
import random

from ibots import utils
from ibots.base import AbstractBasicBot

DIR = os.path.dirname(os.path.realpath(__file__))

UPCOMING_COUNT = 3

ACTIVITY_TITLE = 'Holiday Donations'

ACTIVITY_DESCRIPTION = '''Holiday Bot rewards users who donate on holidays. You can check this
activity to see upcoming holidays Token Ibis randomly celebrate in the
near future (about {quantity} every week on average). If you make a
donation on that day, then you will have a chance to win reward!

## Upcoming Holidays

| Date | Holiday |
|:-----|:--------|
{upcoming}

## Previous Holidays

| Date | Holiday | Donation |
|:-----|:--------|:---------|
{previous}

---

_Think Holiday Bot might be missing an important date? The full list
of days that Holiday Bot knows about is
[here](https://github.com/Tokenibis/ibis-bots/tree/master/bots/holiday/holidays.json).
Holiday Bot is pretty dumb, so only holidays with a fixed annual date
are supported (e.g. Christmas and July 4th, but not Easter or Memorial
Day). If you have another __fixed date__ holiday in mind, then comment
below. Holiday Bot will consider updating the list... and may send a little
something extra your way._

'''

COMMENT_DESCRIPTION = '''Happy {holiday}! In honor of this holiday, {user} has earned a
reward from Holiday Bot. Take a look [here]({reward})

'''

REWARD_DESCRIPTION = '''Thank you for making a [donation]({donation}) today.
{description}

---

_You can read more about it [here]({link})._

'''


class HolidayBot(AbstractBasicBot):
    def run(self, reward_amount, quantity):
        self.reward_amount = reward_amount
        self.quantity = quantity

        # load list of holidays
        with open(os.path.join(DIR, 'holidays.json')) as fd:
            self.holidays = json.load(fd)

        try:
            for i in range(len(self.holidays) - 1):
                assert (
                    self.holidays[i]['date'],
                    self.holidays[i]['id'],
                ) < (
                    self.holidays[i + 1]['date'],
                    self.holidays[i + 1]['id'],
                )
        except AssertionError:
            self.logger.warn('Holiday file is not sorted')
            self.holidays.sort(key=lambda x: (x['date'], x['id']))

        current = utils.localtime()

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
                scratch=json.dumps(
                    {
                        'upcoming': [],
                        'previous': []
                    },
                    indent=2,
                ),
            )
        activity = self.update_activity(activity, current)

        while True:
            holiday = json.loads(activity['scratch'])['upcoming'][0]
            start = utils.localtime(holiday['start'])

            if current >= utils.day_start(start, offset=1):

                reward_list = [
                    x for x in self.reward_list(
                        user=self.id,
                        related_activity=activity['id'],
                        created_after=str(utils.day_start(start, offset=1)),
                    ) if json.loads(x['scratch'])['holiday'] == holiday['id']
                ]

                # if haven't made a reward, then make a reward
                if reward_list:
                    assert len(reward_list) == 1
                    reward = reward_list[0]
                else:
                    reward_candidates = {}
                    for x in self.donation_list(
                            created_after=str(start),
                            created_before=str(
                                utils.day_start(
                                    start,
                                    offset=1,
                                )),
                    ):
                        if x['user']['id'] not in reward_candidates:
                            reward_candidates[x['user']['id']] = []
                        reward_candidates[x['user']['id']].append(x)

                    if reward_candidates:
                        donation = random.choice(
                            random.choice(list(reward_candidates.items()))[1])

                        reward = self.reward_create(
                            target=donation['user']['id'],
                            description=REWARD_DESCRIPTION.format(
                                donation=self.get_app_link(donation['id']),
                                description=holiday['description'],
                                link=holiday['link'],
                            ),
                            amount=reward_amount,
                            related_activity=activity['id'],
                            scratch=json.dumps(
                                {
                                    'holiday':
                                    holiday['id'],
                                    'donation':
                                    donation['id'],
                                    'user_name':
                                    donation['user']['first_name'],
                                    'target_name':
                                    donation['target']['first_name'],
                                },
                                indent=2,
                            ),
                        )
                    else:
                        activity = self.update_activity(activity, current, {})
                        continue

                reward_scratch = json.loads(reward['scratch'])
                comment_list = self.comment_list(
                    parent=reward_scratch['donation'],
                    user=self.id,
                )

                if not comment_list:
                    self.comment_create(
                        parent=reward_scratch['donation'],
                        description=COMMENT_DESCRIPTION.format(
                            holiday=holiday['name'],
                            user=reward_scratch['user_name'],
                            reward=self.get_app_link(reward['id']),
                        ),
                    )

                activity = self.update_activity(activity, current, reward)

            # wait until the end of the next upcoming holiday
            now = utils.localtime()
            self.api_wait(
                timeout=(utils.day_start(
                    utils.localtime(
                        json.loads(activity['scratch'])['upcoming'][0]
                        ['start']),
                    offset=1,
                ) - now).total_seconds())

            current = utils.localtime()

    def update_activity(self, activity, time, reward=None):
        scratch = json.loads(activity['scratch'])
        if reward is not None and scratch['upcoming']:
            scratch['previous'].append(scratch['upcoming'].pop(0))
            scratch['previous'][-1]['reward_link'] = self.get_app_link(
                reward['id']) if reward else None
            scratch['previous'][-1]['donation_link'] = self.get_app_link(
                json.loads(reward['scratch'])['donation']) if reward else None

        while len(scratch['upcoming']) < UPCOMING_COUNT:

            # Ridiculous that bisect doesn't support custom keys
            if not scratch['upcoming']:
                index = 0
                for i, x in enumerate(self.holidays):
                    if x['date'] > '--{:02d}-{:02d}'.format(
                            time.month,
                            time.day,
                    ):
                        index = i
                        break
            else:
                for i, x in enumerate(self.holidays):
                    if scratch['upcoming'][-1]['id'] == x['id']:
                        index = i
                        break

            while True:
                index += 1
                if random.random() < 52 * self.quantity / len(self.holidays):
                    holiday = self.holidays[index % len(self.holidays)]
                    break

            def _next_date(date):
                candidate = utils.day_start(time).replace(
                    month=int(date[2:4]),
                    day=int(date[5:7]),
                )

                return candidate if candidate >= utils.day_start(
                    time) else candidate.replace(year=candidate.year + 1)

            scratch['upcoming'].append({
                'id':
                holiday['id'],
                'name':
                holiday['name'],
                'description':
                holiday['description'],
                'link':
                holiday['link'],
                'start':
                str(_next_date(holiday['date'])),
            })

        activity = self.activity_update(
            id=activity['id'],
            title=ACTIVITY_TITLE,
            description=ACTIVITY_DESCRIPTION.format(
                quantity=self.quantity,
                upcoming='\n'.join('|{}&nbsp;&nbsp;|[{}]({})|'.format(
                    utils.localtime(x['start']).strftime('%A, %B %d'),
                    x['name'],
                    x['link'],
                ) for x in scratch['upcoming']),
                previous='\n'.join(
                    '|{}&nbsp;&nbsp;|[{}]({})&nbsp;&nbsp;|{}|'.format(
                        str(utils.localtime(x['start']).date()).replace('-', '.'),
                        x['name'],
                        x['link'],
                        '[link]({})'.format(x['donation_link'])
                        if x['donation_link'] else 'none',
                    ) for x in reversed(scratch['previous'])),
            ),
            reward_min=self.reward_amount,
            scratch=json.dumps(scratch, indent=2),
        )

        return activity
