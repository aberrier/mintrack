import pydantic


class AccountsConfig(pydantic.BaseModel):
    # While no user exists, the login page offers to create the first admin.
    setup: bool = True
