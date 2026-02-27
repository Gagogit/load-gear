"""Entry point: python -m load_gear"""

import uvicorn

from load_gear.core.config import get_config


def main():
    config = get_config()
    uvicorn.run(
        "load_gear.api.app:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
        log_level=config.server.log_level,
    )


if __name__ == "__main__":
    main()
