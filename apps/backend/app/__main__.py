from .api import create_app
from .core.server import run


def main() -> None:
    run(create_app)


if __name__ == "__main__":
    main()
