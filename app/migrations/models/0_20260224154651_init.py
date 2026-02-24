from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "users" (
    "id" BIGINT NOT NULL PRIMARY KEY,
    "username" VARCHAR(34),
    "first_name" VARCHAR(64),
    "last_name" VARCHAR(64),
    "photo_url" VARCHAR(256),
    "role" SMALLINT NOT NULL DEFAULT 0,
    "license_end_date" TIMESTAMPTZ,
    "balance" BIGINT NOT NULL DEFAULT 0,
    "ref_code" VARCHAR(8) UNIQUE,
    "or_api_key" VARCHAR(256),
    "or_api_hash" VARCHAR(256),
    "or_model" VARCHAR(256),
    "referred_by_id" BIGINT REFERENCES "users" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_users_usernam_266d85" ON "users" ("username");
COMMENT ON COLUMN "users"."role" IS 'USER: 0\nADMIN: 7';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "eJztmFtv2jAUx78KylMndRUN1/WNtnRlBTpx2aZ2VWQSE6wmNnWctajiu882uSewwGClE2"
    "/J3+fE5/xi+yTnVbGJAS3nZOhAqpwVXhUMbMgvYvpxQQHTaagKgYGRJQ1dbiEVMHIYBTrj"
    "4hhYDuSSAR2doilDBHMVu5YlRKJzQ4TNUHIxenKhxogJ2UQGcv/AZYQN+AId/3b6qI0RtI"
    "xYnMgQc0tdY7Op1M6R2cLsStqKCUeaTizXxqH9dMYmBAcOCDOhmhBDChg0IimICL1UfWkR"
    "LRcYdWEQphEKBhwD12KRlHNy0AkWDHk4jkzSFLN8/KSqpVJNLZaq9Uq5VqvUi3VuK0NKD9"
    "Xmi4xDIotHSS6tz63uQGRK+ItavD4hzKUPYGDhJYGHhMULltcpzhcTQLMpR30SrHmCOVh7"
    "JAPUvsnuWNvgRbMgNtmE35bKKzB+a/Qurhu9o1L5Q5xl1xtR5ZCgGlIcI+owbV2Oca8dkQ"
    "x36y5QVvOgrC5HWU2htMAGJGNOB5BybDohjGgutdYBGXN6lyDVSjUHSW61FKUci7OkxMpY"
    "j7wMNbFrS5ItHhLAOkwR9V23U5Ty0CymUCrDfrPHB37ixmWn1T0r1JR1SlRJrVWDoiRuVp"
    "WhfqfRbvt1J7KtkQ6xAzWIDY0Xowyal1xlyIZLdniGfwKp4T3gxL/Yy9W6At2g1Wn2B43O"
    "VxG47ThPluTSGDTFiCrVWUI9Sq7j4CGF763BdUHcFu5uu00JjDjMpHLG0G5wp4iYgMs3Pi"
    "bPGjCiafuyL8Ve6ghY/prP/40WcXrLPbGX32mREweOOTNjrSoY9dnK2b3zT+DYyV3PcW7X"
    "l57a9eSZTagGpkh7hLN1GMa9DhUwQXMCnMkGOH23A88IT/m7vSbMwOdAMnJSQkqhoY1m2r"
    "r9grTvRiXpDbj+s6IkejPjx8zeQYReGvsVoRCZ+AbOUt/HCcaJZtTesZ77q8ZXwygoeA66"
    "VhmLiSfJU4NMptlvDgrdYbutSKQjoD8+A2poK9mCRTsusaA916ubHrSAzOb/gSrhEJVEoM"
    "RwpYds1U4qAANTRi3mFjN5NBqQIn2iZHRCvZHjVb1QENrsTTP0rzuh3pvfg0aoelquleul"
    "ajk4wgJl1cn15xbnL0gdb5PkrbQRl40K7Ub/KNuttJVclbayotJWkpVWbI01IHrm7xPgab"
    "GYAyC3WgpQjsUB8hkZXOzBOMQv/dtuNsSISwLkEPME7w2ks+OChRz2sJ9YV1AUWcdaHT68"
    "o07jR5LrRfv2PNnDEA84z/pGWV5ht19e5r8B+kq8oA=="
)
