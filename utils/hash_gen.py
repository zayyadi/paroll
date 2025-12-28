# django_password_utils.py
import base64
import hashlib
import secrets


def make_django_password(
    password: str,
    salt: str | None = None,
    iterations: int = 260000,
    use_django_if_available: bool = True,
) -> str:
    """
    Produce a Django-compatible password hash (pbkdf2_sha256$iterations$salt$hash).

    Behavior:
    - If Django is installed and use_django_if_available is True, this will call
      django.contrib.auth.hashers.make_password to get the canonical hash.
    - Otherwise a pure-Python PBKDF2-SHA256 hash is computed that is compatible
      with Django's pbkdf2_sha256 hasher (derived-key base64-encoded).

    Parameters
    ----------
    password : str
        Plaintext password.
    salt : Optional[str]
        Salt to use. If None, a cryptographically secure salt is generated.
    iterations : int
        Number of PBKDF2 iterations (Django default around 260000 in recent versions).
    use_django_if_available : bool
        Try to use Django's implementation if Django is installed.

    Returns
    -------
    str
        A Django-style password hash string, e.g.
        "pbkdf2_sha256$260000$somesalt$base64hash"
    """
    if salt is None:
        # generate a URL-safe salt and trim to reasonable length
        salt = secrets.token_urlsafe(12)

    # Try to use Django if present and requested
    if use_django_if_available:
        try:
            from django.contrib.auth.hashers import make_password as dj_make_password

            # dj_make_password returns the full string with algorithm prefix
            # Passing hasher='pbkdf2_sha256' explicitly ensures algorithm
            return dj_make_password(password, salt=salt, hasher="pbkdf2_sha256")
        except Exception:
            # If Django not installed (ImportError) or something else,
            # we'll fall back to the pure-Python implementation below.
            pass

    # Pure-Python PBKDF2-SHA256 implementation compatible with Django formatting.
    # Derived key length: 32 bytes for SHA-256
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
        dklen=32,
    )
    hash_b64 = base64.b64encode(dk).decode("ascii").strip()

    return f"pbkdf2_sha256${iterations}${salt}${hash_b64}"


# --- Example usage ---
if __name__ == "__main__":
    # single password
    print(make_django_password("S3cureP@ssw0rd"))

    # generate unique hashes for many users, starting from some id
    import json
    from faker import Faker

    fake = Faker()

    def gen_user_with_hash(uid):
        pwd = fake.password(
            length=12, special_chars=True, digits=True, upper_case=True, lower_case=True
        )
        print(f"User {uid} password: {pwd}")
        hashed = make_django_password(pwd)  # uses fallback or Django if available
        return {
            "id": uid,
            "email": fake.email(),
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "password": hashed,
            "date_joined": fake.date_time_between(
                start_date="-2y", end_date="now"
            ).strftime("%Y-%m-%d %H:%M:%S"),
        }

    # Example: create 5 sample users to demonstrate
    with open("users.json", "w") as f:
        users = [gen_user_with_hash(i) for i in range(6, 106)]
        json.dump(users, f, indent=4)

    print("✅ 100 mock custom users saved to users.json")
