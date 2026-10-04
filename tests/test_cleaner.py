import pandas as pd

from csv_cleaner.cleaner import CleanerConfig, clean_dataframe, standardize_column_name


def test_standardize_column_name():
    assert standardize_column_name("  Customer ID ") == "customer_id"
    assert standardize_column_name("E-mail Address") == "e_mail_address"


def test_whitespace_stripped_before_dedup():
    df = pd.DataFrame({"Name ": ["  Ann ", "Ann"], "Score": [1, 1]})
    cleaned, report = clean_dataframe(df)
    assert report.duplicates_removed == 1
    assert len(cleaned) == 1

from csv_cleaner.cleaner import detect_delimiter, detect_encoding


def test_detect_delimiter():
    assert detect_delimiter("a;b;c\n1;2;3\n") == ";"
    assert detect_delimiter("a\tb\tc\n1\t2\t3\n") == "\t"


def test_detect_encoding_cp1252():
    assert detect_encoding("José".encode("cp1252")) == "cp1252"


def test_currency_text_becomes_numeric():
    df = pd.DataFrame({"price": ["$1,200", "$950", None]})
    cleaned, report = clean_dataframe(df)
    assert report.converted_types["price"] == "numeric"
    assert cleaned["price"].isna().sum() == 0


def test_whole_numbers_stay_integers():
    df = pd.DataFrame({"age": [30.0, None, 40.0, 50.0]})
    cleaned, _ = clean_dataframe(df)
    assert str(cleaned["age"].dtype) == "Int64"
    assert cleaned["age"].iloc[1] == 40


def test_bad_dates_counted():
    df = pd.DataFrame({"signup_date": ["2024-01-05", "garbage"]})
    cleaned, report = clean_dataframe(df)
    assert report.unparseable_dates["signup_date"] == 1
def test_median_fill():
    df = pd.DataFrame({"x": [1.0, None, 3.0, 5.0]})
    cleaned, _ = clean_dataframe(df, CleanerConfig(fill_method="median"))
    assert cleaned["x"].isna().sum() == 0
    assert cleaned["x"].iloc[1] == 3.0