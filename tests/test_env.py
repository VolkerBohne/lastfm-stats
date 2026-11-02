from lastfm_stats.env import load_dotenv, merge_dotenv, parse_dotenv


def test_parse_dotenv_handles_comments_quotes_and_export():
    text = """
    # a comment
    LASTFM_USERNAME=rj
    export LASTFM_API_KEY="abc123"
    EMPTY=
    SPACED = value with spaces
    SINGLE='quoted value'
    INLINE=value # trailing comment
    HASH='value # kept'
    NOVALUE
    """

    values = parse_dotenv(text)

    assert values == {
        "LASTFM_USERNAME": "rj",
        "LASTFM_API_KEY": "abc123",
        "EMPTY": "",
        "SPACED": "value with spaces",
        "SINGLE": "quoted value",
        "INLINE": "value",
        "HASH": "value # kept",
    }


def test_load_dotenv_missing_file_returns_empty_mapping(tmp_path):
    assert load_dotenv(tmp_path / "missing.env") == {}


def test_load_dotenv_reads_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LASTFM_USERNAME=rj\nLASTFM_API_KEY=secret\n")

    assert load_dotenv(env_file) == {
        "LASTFM_USERNAME": "rj",
        "LASTFM_API_KEY": "secret",
    }


def test_merge_dotenv_keeps_existing_environment_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LASTFM_USERNAME=file\nLASTFM_API_KEY=file\n")

    merged = merge_dotenv(
        {"LASTFM_API_KEY": "environment"},
        env_file,
    )

    assert merged == {
        "LASTFM_USERNAME": "file",
        "LASTFM_API_KEY": "environment",
    }
