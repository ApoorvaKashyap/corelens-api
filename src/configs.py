"""Global application settings and configuration variables."""

from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a .env file.

    Precedence (highest → lowest):
        1. Real environment variables (e.g. ``export REDIS_HOST=...``)
        2. Values in ``.env`` in the project root
        3. The defaults declared below

    AWS secret fields use :class:`pydantic.SecretStr` so their values are
    never accidentally logged or included in ``model_dump()`` output.
    """

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: SecretStr = SecretStr("")
    aws_region: str = "ap-south-1"
    s3_base: str = ""

    # Working Directory
    temp_path: str = "/tmp/"  # noqa: S108
    data_root: str = "./data/"

    # Farm boundaries are partitioned as <farm_data_root>/<state>/<district>/<block>/*.parquet
    farm_data_root: str = "./data/farm_boundaries/"

    # One literal "<state>/<district>/<block>" path, sampled once at startup to
    # generate the Farm GraphQL annual/monthly types from its real schema — the
    # same schema-drives-the-type approach MWS/Tehsil/Waterbody use, applied to
    # farms. Required (no default): every block is expected to share the same
    # schema, so the app should fail to start rather than silently pick one.
    farm_schema_sample_block: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def aws_storage_options(self) -> dict[str, Any]:
        """Credentials to pass as core_lens's entity ``storage_options``.

        Only meaningful when data_root/farm_data_root are cloud URIs (e.g.
        ``s3://bucket/prefix``) rather than local paths — core_lens forwards
        this dict to polars' scan_parquet verbatim (no key translation), so
        the keys here must be the ones polars/object_store actually recognize
        (aws_region/aws_access_key_id/aws_secret_access_key), not the generic
        region/access_key/secret_key names BaseEntity's docstring suggests.

        Without an explicit key, this returns aws_skip_signature=true rather
        than an empty/None value — storage_options=None lets object_store fall
        through to the full AWS credential-discovery chain, which ends in an
        EC2 instance-metadata (IMDS) lookup that hangs/fails off of EC2 and
        produces a confusing error instead of a clean anonymous request.
        """
        if self.aws_access_key_id:
            return {
                "aws_region": self.aws_region,
                "aws_access_key_id": self.aws_access_key_id,
                "aws_secret_access_key": self.aws_secret_access_key.get_secret_value(),
            }
        return {"aws_region": self.aws_region, "aws_skip_signature": "true"}


settings = Settings()
