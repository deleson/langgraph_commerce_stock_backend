from pwdlib import PasswordHash

from app.core.exceptions import BadRequestException

password_hash = PasswordHash.recommended()

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128



def validate_password_strength(password:str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise BadRequestException(
            message=f"password must be at least {MIN_PASSWORD_LENGTH} characters long",
            details=[{"field":"password","reason":"password is too short"}]
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise BadRequestException(
            message=f"password must be at most {MAX_PASSWORD_LENGTH} characters long",
            details=[{"field":"password","reason":"password is too long"}]
        )

    if password.isspace():
        raise BadRequestException(
            message="password cannot be blank",
            details=[{"field": "password", "reason": "password cannot contain only whitespace"}],
        )


def hash_password(password:str) -> str:
    validate_password_strength(password)
    return password_hash.hash(password)

def verify_password(plain_password:str,hashed_password:str) -> bool:
    return password_hash.verify(plain_password,hashed_password)