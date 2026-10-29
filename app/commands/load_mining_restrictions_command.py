from pathlib import Path

from sqlalchemy.orm import Session

from app.loaders.mining_restriction_loader import MiningRestrictionLoader


class LoadMiningRestrictionsCommand:
    def __init__(self, session: Session, file: Path | str, **options):
        self.loader = MiningRestrictionLoader(session, file, **options)

    def execute(self) -> dict:
        return self.loader.execute()
