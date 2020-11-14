import json
import random

from ibots import utils
from ibots.base import AbstractBasicBot

ACTIVITY_TITLE = 'Donation Streaks'

ACTIVITY_DESCRIPTION = '''Consistency is the key to progress. Every week, Streak Bot will
randomly select a reward recipient from everyone who has made
donations for {minimum_streak} or more consecutive weeks worth
${amount} for each week.

## Active Streaks

Congratulations to Token Ibis's most active users. Streak Bot sees and
appreciates your dedication to consistent impact.

| Weeks &nbsp; &nbsp; &nbsp; | Dollars &nbsp; &nbsp; &nbsp; | Donor &nbsp; &nbsp; &nbsp; |
|:-|:-|:-|
{streaks}

'''

REWARD_DESCRIPTION = '''Hi {name}, thanks for going {streak} straight weeks of making an
impact in the community. Keep it up!

'''


class StreakBot(AbstractBasicBot):
    def run(
            self,
            rewards_per_week,
            reward_multiplier,
            minimum_streak,
            ubp_weekday,
            reward_weekday,
    ):
        self.ubp_weekday = ubp_weekday

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
                reward_min=0,
                active=True,
            )

        while True:
            now = utils.localtime()

            # only execute logic if Streak Bot hasn't made a reward this epoch
            if not self.reward_list(
                    user=self.id,
                    created_after=str(utils.epoch_start(reward_weekday, now))):
                leaderboard = []

                # go through all of last week's donations
                for user in [
                        dict(y) for y in set(
                            tuple(x['user'].items())
                            for x in self.donation_list(
                                created_after=str(
                                    utils.epoch_start(
                                        ubp_weekday,
                                        now,
                                        offset=-1,
                                    )),
                                created_before=str(
                                    utils.epoch_start(
                                        ubp_weekday,
                                        now,
                                    )),
                            ))
                ]:
                    self.logger.debug('person')
                    streak, amount = self.check_streak(user, now)
                    if streak < minimum_streak:
                        continue

                    leaderboard.append({
                        'user': user,
                        'streak': streak,
                        'amount': amount,
                    })

                leaderboard.sort(
                    key=lambda x: (x['streak'], x['amount']),
                    reverse=True,
                )

                self.logger.debug('Leaderboard: ' + json.dumps(leaderboard))

                # update activity with new streak information
                activity = self.activity_update(
                    id=activity['id'],
                    title=ACTIVITY_TITLE,
                    description=ACTIVITY_DESCRIPTION.format(
                        minimum_streak=minimum_streak,
                        weekday=reward_weekday,
                        amount='{:.2f}'.format(reward_multiplier / 100),
                        streaks='\n'.join('| {} | ${:.2f} | @{} |'.format(
                            x['streak'],
                            x['amount'] / 100,
                            x['user']['username'],
                        ) for x in leaderboard),
                    ),
                    reward_min=reward_multiplier * minimum_streak,
                    reward_range=max(
                        0,
                        reward_multiplier *
                        (leaderboard[0]['streak'] - minimum_streak)
                        if leaderboard else 0,
                    ),
                )

                # send out the reward to a random user
                if leaderboard:
                    winner = random.choice(leaderboard)
                    self.reward_create(
                        target=winner['user']['id'],
                        amount=reward_multiplier * winner['streak'],
                        related_activity=activity['id'],
                        description=REWARD_DESCRIPTION.format(
                            name=winner['user']['first_name'],
                            streak=winner['streak'],
                        ),
                    )

            # wait until next Wednesday
            self.api_wait(
                timeout=(utils.epoch_start(
                    reward_weekday,
                    now,
                    offset=1,
                ) - now).total_seconds())

    def check_streak(self, user, now):
        offset = 0
        streak = 0
        amount = 0

        while True:
            donations = self.donation_list(
                user=user['id'],
                created_after=str(
                    utils.epoch_start(
                        self.ubp_weekday,
                        now,
                        offset=offset - 1,
                    )),
                created_before=str(
                    utils.epoch_start(
                        self.ubp_weekday,
                        now,
                        offset=offset,
                    )),
            )
            if not donations:
                break

            offset -= 1
            streak += 1
            amount += sum(x['amount'] for x in donations)

        return streak, amount
