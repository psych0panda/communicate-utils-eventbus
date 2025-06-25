import re

TO_SNAKE_RE = re.compile(
    r"((?<=[a-z0-9])[A-Z]|(?!^|(?<=[./]))[A-Z_](?=[a-z]))"
)
EXTRA_UNDERSCORE_RE = re.compile(r"__+")
SPLIT_RE = re.compile(r"(?=[./])|(?<=[./])")


def decapitalize(word: str) -> str:
    return word[0].lower() + word[1:] if word else word


def _camel_to_snake(word: str) -> str:
    return TO_SNAKE_RE.sub(r"_\1", word).lower()


def _snake_to_camel(word: str) -> str:
    return word[0] + decapitalize(
        "".join([x for x in word.title()[1:] if x.isalnum()])
    )


def camelize(word: str) -> str:
    _word = _camel_to_snake(word)
    return "".join([_snake_to_camel(x) for x in SPLIT_RE.split(_word)])


def decamelize(word: str) -> str:
    _word = _camel_to_snake(word)
    return EXTRA_UNDERSCORE_RE.sub(r"_", _word)
