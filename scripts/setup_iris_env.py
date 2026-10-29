"""Create local task settings without printing or overwriting passwords."""

import os
from pathlib import Path
import secrets


def main():
    file = Path(".env.iris")
    uid = str(os.getuid()) if hasattr(os, "getuid") else "1000"
    gid = str(os.getgid()) if hasattr(os, "getgid") else "1000"

    if not file.exists():
        password = secrets.token_urlsafe(32)
        contents = (
            f"IRIS_DB_PASSWORD={password}\n"
            f"IRIS_DATABASE_URL=postgresql+psycopg2://hitesh_soneji:{password}@127.0.0.1:4000/iris_geo_sn\n"
            f"IRIS_UID={uid}\nIRIS_GID={gid}\n"
        )
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(contents)
        print("Created .env.iris with a local password (not printed).")
    else:
        contents = file.read_text()
        keys = {line.split("=", 1)[0].strip() for line in contents.splitlines() if "=" in line}
        additions = []
        for key, value in (("IRIS_UID", uid), ("IRIS_GID", gid)):
            if key not in keys:
                additions.append(f"{key}={value}\n")
        if additions:
            with file.open("a") as handle:
                if contents and not contents.endswith("\n"):
                    handle.write("\n")
                handle.writelines(additions)
        print("Kept existing credentials; checked local report-file ownership settings.")

    Path("reports").mkdir(exist_ok=True)


if __name__ == "__main__":
    main()
