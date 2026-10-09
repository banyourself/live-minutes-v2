from server.app import db, jobs
from server.app.settings import settings


def main():
    settings.validate()
    db.init_db()
    print("Live Minutes worker started")
    jobs.loop()


if __name__ == "__main__":
    main()
