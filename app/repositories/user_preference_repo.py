from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_preference import UserPreference


class UserPreferenceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user_id(self, user_id: int) -> UserPreference | None:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_default(self, user_id: int) -> UserPreference:
        preference = UserPreference(
            user_id=user_id,
            risk_preference="balanced",
            timezone="Asia/Shanghai",
            daily_report_enabled=False,
            abnormal_alert_enabled=False,
            default_watchlist_alert_enabled=False,
        )
        self.db.add(preference)
        self.db.commit()
        self.db.refresh(preference)
        return preference

    def save(self, preference: UserPreference) -> UserPreference:
        self.db.add(preference)
        self.db.commit()
        self.db.refresh(preference)
        return preference