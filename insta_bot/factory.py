from insta_bot.session import BotClient, ChallengePending


class AccountFactory:
    """Hesap adindan baglanmis BotClient uretir (CLI ve API ortak kullanim)."""

    def __init__(self, config, repo, logger):
        self.config = config
        self.repo = repo
        self.logger = logger

    def connect(self, name, force=False, challenge_callback=None, verification_callback=None):
        acc = self.config.account(name)
        if not acc:
            raise ValueError(f"Hesap tanimli degil: {name} (accounts.yaml)")
        bc = BotClient(self.config, self.repo, self.logger, acc)
        try:
            return bc.connect(force=force, challenge_callback=challenge_callback,
                              verification_callback=verification_callback)
        except ChallengePending:
            raise
