from dataclasses import replace

import pytest

from config.settings import Settings
from services.evaluation import EvalEnv


@pytest.fixture()
def env(tmp_path):
    settings = replace(Settings.from_env(load_env_file=False), model_provider="mock",
                       database_url=f"sqlite:///{tmp_path}/test.db")
    e = EvalEnv(settings)
    yield e
    e.close()
