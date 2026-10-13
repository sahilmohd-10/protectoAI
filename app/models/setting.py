from app.extensions import db


class Setting(db.Model):
    """System runtime settings and configuration overrides."""
    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    @classmethod
    def get_value(cls, key: str, default=None):
        """Retrieve setting value or fallback to default."""
        item = cls.query.filter_by(key=key).first()
        return item.value if item else default

    @classmethod
    def set_value(cls, key: str, value: str, description: str = None):
        """Upsert a setting value."""
        item = cls.query.filter_by(key=key).first()
        if item:
            item.value = str(value)
            if description:
                item.description = description
        else:
            item = cls(key=key, value=str(value), description=description)
            db.session.add(item)
        db.session.commit()
        return item

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
        }

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"
