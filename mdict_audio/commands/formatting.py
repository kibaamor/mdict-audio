def key_extension(key, missing=""):
    name = key.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if ext:
            return ext
    return missing


def reader_suffix(reader):
    suffix = " (v%s" % reader.version_text
    if reader.is_encrypted:
        suffix += ", encrypted"
    return suffix + ")"
