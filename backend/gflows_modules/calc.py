import pandas as pd
import exchange_calendars as xcals
import numpy as np
import orjson
import requests
import modules.stats as stats
from yfinance import Ticker
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo
from dateparser.date import DateDataParser
from warnings import simplefilter
from calendar import monthrange
from cachetools import cached, TTLCache
from pathlib import Path
from os import getcwd
from re import compile

# Ignore warning for NaN values in dataframe
simplefilter(action="ignore", category=RuntimeWarning)

pd.options.display.float_format = "{:,.4f}".format

# Precompile regex patterns for performance
_strike_regex = compile(r"\d[A-Z](\d+)\d\d\d")
_exp_date_regex = compile(r"(\d{6})[CP]")


@cached(cache=TTLCache(maxsize=16, ttl=60 * 60 * 4))  # in-memory cache for 4 hrs
def is_third_friday(date, tz):
    _, last = monthrange(date.year, date.month)
    first = datetime(date.year, date.month, 1)
    last = datetime(date.year, date.month, last)
    result = xcals.get_calendar("XNYS", start=first, end=last)
    result = result.sessions.to_pydatetime()
    found = [False, False]
    for i in result:
        if i.weekday() == 4 and 15 <= i.day <= 21 and i.month == date.month:
            # Third Friday
            found[0] = i.replace(tzinfo=ZoneInfo(tz)) + timedelta(hours=16)
        elif i.weekday() == 3 and 15 <= i.day <= 21 and i.month == date.month:
            # Thursday alternative
            found[1] = i.replace(tzinfo=ZoneInfo(tz)) + timedelta(hours=16)
    # returns Third Friday if market open,
    # else if market closed returns the Thursday before it
    return (found[0], result) if found[0] else (found[1], result)


@cached(cache=TTLCache(maxsize=16, ttl=60 * 60 * 4))  # in-memory cache for 4 hrs
def get_next_monthly_opex(first_expiry, tz, max_months_ahead=6):
    """
    Find the next monthly OPEX that hasn't expired yet.
    Searches up to max_months_ahead months from first expiration.
    """

    # Generate candidate months starting from first_expiry month
    base_date = first_expiry.replace(day=1)

    for month_offset in range(max_months_ahead):
        check_date = base_date + relativedelta(months=month_offset)
        monthly_opex, _ = is_third_friday(check_date, tz)

        if monthly_opex and first_expiry <= monthly_opex:
            return monthly_opex

    # Fallback: return the OPEX for the first expiry month even if expired
    return is_third_friday(first_expiry, tz)[0]


@cached(cache=TTLCache(maxsize=16, ttl=60 * 60 * 4))  # in-memory cache for 4 hrs
def fetch_treasury_yield_curve(target_date=None):
    """
    Fetch treasury yield curve rates for multiple tenors.
    Primary: FRED (Federal Reserve - exact maturities)
    Fallback: yfinance (3mo, 5yr, 10yr)
    Last resort: Neutral 3% centered upward-sloping curve

    Args:
        target_date: Optional datetime object to fetch rates for a specific date.
                    If None, fetches the most recent rates.

    Returns:
        dict: Mapping of tenor names to yield rates (as decimals)
        Keys: '1mo', '3mo', '6mo', '1yr', '2yr', '5yr', '10yr'
    """

    # Primary: Try FRED first (official Federal Reserve data)
    try:
        series_ids = {
            "1mo": "DGS1MO",
            "3mo": "DGS3MO",
            "6mo": "DGS6MO",
            "1yr": "DGS1",
            "2yr": "DGS2",
            "5yr": "DGS5",
            "10yr": "DGS10",
        }

        # Set date range
        if target_date:
            end_date = target_date + timedelta(days=1)
            start_date = target_date - timedelta(days=7)
        else:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)

        rates = {}
        base_url = "https://fred.stlouisfed.org/graph/fredgraph.csv"

        for tenor, series_id in series_ids.items():
            try:
                params = {
                    "id": series_id,
                    "cosd": start_date.strftime("%Y-%m-%d"),
                    "coed": end_date.strftime("%Y-%m-%d"),
                }
                response = requests.get(base_url, params=params, timeout=10)
                response.raise_for_status()

                lines = response.text.strip().split("\n")
                if len(lines) >= 2:
                    if target_date:
                        target_str = target_date.strftime("%Y-%m-%d")
                        # Try exact date match first
                        for line in lines[1:]:
                            parts = line.split(",")
                            if (
                                len(parts) == 2
                                and parts[0] == target_str
                                and parts[1] not in ["", ".", "NA"]
                            ):
                                rates[tenor] = float(parts[1]) / 100
                                break
                        # If no exact match, find closest previous date
                        if tenor not in rates:
                            for line in reversed(lines[1:]):
                                parts = line.split(",")
                                if (
                                    len(parts) == 2
                                    and parts[1] not in ["", ".", "NA"]
                                    and parts[0] <= target_str
                                ):
                                    rates[tenor] = float(parts[1]) / 100
                                    break
                    else:
                        # Get most recent rate
                        for line in reversed(lines[1:]):
                            parts = line.split(",")
                            if len(parts) == 2 and parts[1] not in ["", ".", "NA"]:
                                rates[tenor] = float(parts[1]) / 100
                                break
            except:
                continue

        if len(rates) >= 3:
            return rates

    except Exception as e:
        print(f"FRED failed: {e}")

    # Fallback: Try yfinance
    try:
        rates = {}
        if target_date:
            start_date = target_date - timedelta(days=5)
            end_date = target_date + timedelta(days=1)
        else:
            start_date = None
            end_date = None

        # Fetch ^IRX (3mo), ^FVX (5yr), ^TNX (10yr)
        for symbol, tenor in [("^IRX", "3mo"), ("^FVX", "5yr"), ("^TNX", "10yr")]:
            try:
                if start_date:
                    data = Ticker(symbol).history(start=start_date, end=end_date)
                else:
                    data = Ticker(symbol).history(period="5d")
                if not data.empty:
                    rates[tenor] = data.tail(1)["Close"].item() / 100
            except:
                pass

        if len(rates) >= 2:
            return rates
    except:
        pass

    # Last resort: Default (neutral upward-sloping curve)
    # Based on ~3% mid-curve (reasonable across cycles)
    return {
        "1mo": 0.025,  # 2.5% - short-term
        "3mo": 0.027,  # 2.7%
        "6mo": 0.029,  # 2.9%
        "1yr": 0.030,  # 3.0%
        "2yr": 0.031,  # 3.1%
        "5yr": 0.033,  # 3.3%
        "10yr": 0.035,  # 3.5% - long-term
    }


def get_tenor_matched_rate(days_to_expiry, yield_curve):
    """
    Get the appropriate risk-free rate based on days to expiration.
    Falls back to closest available tenor if exact match not found.

    Args:
        days_to_expiry: Number of days until option expiration
        yield_curve: Dictionary of rates from fetch_treasury_yield_curve()

    Returns:
        Risk-free rate (as decimal) appropriate for the tenor
    """
    if not yield_curve:
        return 0.030  # 3.0% default (neutral mid-curve rate)

    # Define tenor preferences in order (primary, fallback1, fallback2, ...)
    if days_to_expiry <= 30:
        tenors = ["1mo", "3mo", "6mo", "1yr"]
    elif days_to_expiry <= 90:
        tenors = ["3mo", "1mo", "6mo", "1yr"]
    elif days_to_expiry <= 180:
        tenors = ["6mo", "3mo", "1yr", "2yr"]
    elif days_to_expiry <= 365:
        tenors = ["1yr", "6mo", "2yr", "5yr"]
    elif days_to_expiry <= 730:
        tenors = ["2yr", "1yr", "5yr", "10yr"]
    elif days_to_expiry <= 1825:
        tenors = ["5yr", "2yr", "10yr"]
    else:
        tenors = ["10yr", "5yr", "2yr"]

    # Return first available tenor from preference list
    for tenor in tenors:
        if tenor in yield_curve:
            return yield_curve[tenor]

    # If none of the preferred tenors exist, return any available rate
    if yield_curve:
        return list(yield_curve.values())[0]

    # Final fallback
    return 0.030  # 3.0% neutral mid-curve rate


def is_parsable(date):
    try:
        datetime.strptime(date.split()[-2], "%H:%M")
        return True
    except ValueError:
        return False


def format_data(data, today_ddt, tzinfo):
    keys_to_keep = ["option", "iv", "open_interest", "volume", "delta", "gamma"]
    data = pd.DataFrame([{k: d[k] for k in keys_to_keep if k in d} for d in data])
    data = pd.concat(
        [
            data.rename(
                columns={
                    "option": "calls",
                    "iv": "call_iv",
                    "open_interest": "call_open_int",
                    "volume": "call_vol",
                    "delta": "call_delta",
                    "gamma": "call_gamma",
                }
            )
            .iloc[0::2]
            .reset_index(drop=True),
            data.rename(
                columns={
                    "option": "puts",
                    "iv": "put_iv",
                    "open_interest": "put_open_int",
                    "volume": "put_vol",
                    "delta": "put_delta",
                    "gamma": "put_gamma",
                }
            )
            .iloc[1::2]
            .reset_index(drop=True),
        ],
        axis=1,
    )
    data["strike_price"] = data["calls"].str.extract(_strike_regex).astype(float)
    data["expiration_date"] = data["calls"].str.extract(_exp_date_regex)
    data["expiration_date"] = pd.to_datetime(
        data["expiration_date"], format="%y%m%d"
    ).dt.tz_localize(tzinfo) + timedelta(hours=16)

    busday_counts = np.busday_count(
        today_ddt.date(),
        data["expiration_date"].values.astype("datetime64[D]"),
    )
    # set DTE. 0DTE options are included in 1 day expirations
    # time to expiration in years (252 trading days)
    data["time_till_exp"] = np.where(busday_counts == 0, 1 / 252, busday_counts / 252)

    data = data.sort_values(by=["expiration_date", "strike_price"]).reset_index(
        drop=True
    )

    return data


def calc_exposures(
    option_data,
    ticker,
    expir,
    first_expiry,
    next_monthly_opex,
    this_monthly_opex,
    spot_price,
    today_ddt,
    today_ddt_string,
):
    dividend_yield = 0.0  # assume 0

    # Fetch treasury yield curve for tenor-matching
    # This will always return valid rates (uses fallback chain: FRED → yfinance → default curve)
    yield_curve = fetch_treasury_yield_curve()

    # Calculate days to expiration
    expirations = option_data["expiration_date"]
    days_to_expiry = (expirations - today_ddt).dt.days.to_numpy()

    # Get tenor-matched risk-free rates for each option
    risk_free_rates = np.array(
        [get_tenor_matched_rate(days, yield_curve) for days in days_to_expiry]
    )

    monthly_options_dates = [first_expiry, this_monthly_opex]

    strike_prices = option_data["strike_price"].to_numpy()
    time_till_exp = option_data["time_till_exp"].to_numpy()
    opt_call_ivs = option_data["call_iv"].to_numpy()
    opt_put_ivs = option_data["put_iv"].to_numpy()

    # IMPORTANT: For 0DTE and 1DTE options, use VOLUME instead of OPEN INTEREST
    #
    # Reasoning:
    # - Day -1 EOD volume represents positioning going into expiration day
    # - Day 0 OI often doesn't reflect overnight positioning
    # - Volume gives more accurate picture of exposure for very short-dated options
    #
    # For longer-dated options (2+ DTE), we use standard open interest.
    is_short_dte = days_to_expiry <= 1

    # Use volume for 0DTE/1DTE if available, otherwise fall back to OI
    if "call_vol" in option_data.columns:
        call_open_interest = np.where(
            is_short_dte,
            option_data["call_vol"].fillna(option_data["call_open_int"]).to_numpy(),
            option_data["call_open_int"].to_numpy(),
        )
        put_open_interest = np.where(
            is_short_dte,
            option_data["put_vol"].fillna(option_data["put_open_int"]).to_numpy(),
            option_data["put_open_int"].to_numpy(),
        )
    else:
        # Fallback: use open interest for all (backwards compatibility)
        call_open_interest = option_data["call_open_int"].to_numpy()
        put_open_interest = option_data["put_open_int"].to_numpy()

    nonzero_call_cond = (time_till_exp > 0) & (opt_call_ivs > 0)
    nonzero_put_cond = (time_till_exp > 0) & (opt_put_ivs > 0)
    np_spot_price = np.array([[spot_price]])

    call_dp, call_cdf_dp, call_pdf_dp = stats.calc_dp_cdf_pdf(
        np_spot_price,
        strike_prices,
        opt_call_ivs,
        time_till_exp,
        risk_free_rates,  # Use tenor-matched rates
        dividend_yield,
    )
    put_dp, put_cdf_dp, put_pdf_dp = stats.calc_dp_cdf_pdf(
        np_spot_price,
        strike_prices,
        opt_put_ivs,
        time_till_exp,
        risk_free_rates,  # Use tenor-matched rates
        dividend_yield,
    )

    from_strike = 0.5 * spot_price
    to_strike = 1.5 * spot_price

    # ---=== CALCULATE EXPOSURES ===---
    option_data["call_dex"] = (
        option_data["call_delta"].to_numpy() * call_open_interest * spot_price
    )
    option_data["put_dex"] = (
        option_data["put_delta"].to_numpy() * put_open_interest * spot_price
    )
    option_data["call_gex"] = (
        option_data["call_gamma"].to_numpy()
        * call_open_interest
        * spot_price
        * spot_price
    )
    option_data["put_gex"] = (
        option_data["put_gamma"].to_numpy()
        * put_open_interest
        * spot_price
        * spot_price
        * -1
    )
    option_data["call_vex"] = np.where(
        nonzero_call_cond,
        stats.calc_vanna_ex(
            np_spot_price,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_dp,
            call_pdf_dp,
        )[0],
        0,
    )
    option_data["put_vex"] = np.where(
        nonzero_put_cond,
        stats.calc_vanna_ex(
            np_spot_price,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_dp,
            put_pdf_dp,
        )[0],
        0,
    )
    option_data["call_cex"] = np.where(
        nonzero_call_cond,
        stats.calc_charm_ex(
            np_spot_price,
            opt_call_ivs,
            time_till_exp,
            risk_free_rates,  # Use tenor-matched rates
            dividend_yield,
            "call",
            call_open_interest,
            call_dp,
            call_cdf_dp,
            call_pdf_dp,
        )[0],
        0,
    )
    option_data["put_cex"] = np.where(
        nonzero_put_cond,
        stats.calc_charm_ex(
            np_spot_price,
            opt_put_ivs,
            time_till_exp,
            risk_free_rates,  # Use tenor-matched rates
            dividend_yield,
            "put",
            put_open_interest,
            put_dp,
            put_cdf_dp,
            put_pdf_dp,
        )[0],
        0,
    )
    # Calculate total and scale down
    option_data["total_delta"] = (
        option_data["call_dex"].to_numpy() + option_data["put_dex"].to_numpy()
    ) / 10**9
    option_data["total_gamma"] = (
        option_data["call_gex"].to_numpy() + option_data["put_gex"].to_numpy()
    ) / 10**9
    option_data["total_vanna"] = (
        option_data["call_vex"].to_numpy() - option_data["put_vex"].to_numpy()
    ) / 10**9
    option_data["total_charm"] = (
        option_data["call_cex"].to_numpy() - option_data["put_cex"].to_numpy()
    ) / 10**9

    # group all options by strike / expiration then average their IVs
    df_agg_strike_mean = (
        option_data[["strike_price", "call_iv", "put_iv"]]
        .groupby(["strike_price"])
        .mean(numeric_only=True)
    )
    df_agg_exp_mean = (
        option_data[["expiration_date", "call_iv", "put_iv"]]
        .groupby(["expiration_date"])
        .mean(numeric_only=True)
    )
    # filter strikes / expirations for relevance
    df_agg_strike_mean = df_agg_strike_mean[from_strike:to_strike]
    # df_agg_exp_mean = df_agg_exp_mean[: today_ddt + timedelta(weeks=52)]

    call_ivs = {
        "strike": df_agg_strike_mean["call_iv"].to_numpy(),
        "exp": df_agg_exp_mean["call_iv"].to_numpy(),
    }
    put_ivs = {
        "strike": df_agg_strike_mean["put_iv"].to_numpy(),
        "exp": df_agg_exp_mean["put_iv"].to_numpy(),
    }

    # ---=== CALCULATE EXPOSURE PROFILES ===---
    levels = np.linspace(from_strike, to_strike, 300).reshape(-1, 1)

    totaldelta = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalgamma = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalvanna = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalcharm = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }

    # For each spot level, calculate greek exposure at that point
    call_dp, call_cdf_dp, call_pdf_dp = stats.calc_dp_cdf_pdf(
        levels,
        strike_prices,
        opt_call_ivs,
        time_till_exp,
        risk_free_rates,  # Use tenor-matched rates
        dividend_yield,
    )
    put_dp, put_cdf_dp, put_pdf_dp = stats.calc_dp_cdf_pdf(
        levels,
        strike_prices,
        opt_put_ivs,
        time_till_exp,
        risk_free_rates,  # Use tenor-matched rates
        dividend_yield,
    )
    call_delta_ex = np.where(
        nonzero_call_cond,
        stats.calc_delta_ex(
            levels,
            time_till_exp,
            dividend_yield,
            "call",
            call_open_interest,
            call_cdf_dp,
        ),
        0,
    )
    put_delta_ex = np.where(
        nonzero_put_cond,
        stats.calc_delta_ex(
            levels,
            time_till_exp,
            dividend_yield,
            "put",
            put_open_interest,
            put_cdf_dp,
        ),
        0,
    )
    call_gamma_ex = np.where(
        nonzero_call_cond,
        stats.calc_gamma_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_pdf_dp,
        ),
        0,
    )
    put_gamma_ex = np.where(
        nonzero_put_cond,
        stats.calc_gamma_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_pdf_dp,
        ),
        0,
    )
    call_vanna_ex = np.where(
        nonzero_call_cond,
        stats.calc_vanna_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_dp,
            call_pdf_dp,
        ),
        0,
    )
    put_vanna_ex = np.where(
        nonzero_put_cond,
        stats.calc_vanna_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_dp,
            put_pdf_dp,
        ),
        0,
    )
    call_charm_ex = np.where(
        nonzero_call_cond,
        stats.calc_charm_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            risk_free_rates,  # Use tenor-matched rates
            dividend_yield,
            "call",
            call_open_interest,
            call_dp,
            call_cdf_dp,
            call_pdf_dp,
        ),
        0,
    )
    put_charm_ex = np.where(
        nonzero_put_cond,
        stats.calc_charm_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            risk_free_rates,  # Use tenor-matched rates
            dividend_yield,
            "put",
            put_open_interest,
            put_dp,
            put_cdf_dp,
            put_pdf_dp,
        ),
        0,
    )

    # delta exposure
    totaldelta["all"] = (call_delta_ex.sum(axis=1) + put_delta_ex.sum(axis=1)) / 10**9
    # gamma exposure
    totalgamma["all"] = (call_gamma_ex.sum(axis=1) - put_gamma_ex.sum(axis=1)) / 10**9
    # vanna exposure
    totalvanna["all"] = (call_vanna_ex.sum(axis=1) - put_vanna_ex.sum(axis=1)) / 10**9
    # charm exposure
    totalcharm["all"] = (call_charm_ex.sum(axis=1) - put_charm_ex.sum(axis=1)) / 10**9

    expirs_next_expiry = expirations == first_expiry
    expirs_up_to_monthly_opex = expirations <= next_monthly_opex
    if expir != "0dte":
        # exposure for next expiry
        totaldelta["ex_next"] = (
            np.where(expirs_next_expiry, call_delta_ex, 0).sum(axis=1)
            + np.where(expirs_next_expiry, put_delta_ex, 0).sum(axis=1)
        ) / 10**9
        totalgamma["ex_next"] = (
            np.where(expirs_next_expiry, call_gamma_ex, 0).sum(axis=1)
            - np.where(expirs_next_expiry, put_gamma_ex, 0).sum(axis=1)
        ) / 10**9
        totalvanna["ex_next"] = (
            np.where(expirs_next_expiry, call_vanna_ex, 0).sum(axis=1)
            - np.where(expirs_next_expiry, put_vanna_ex, 0).sum(axis=1)
        ) / 10**9
        totalcharm["ex_next"] = (
            np.where(expirs_next_expiry, call_charm_ex, 0).sum(axis=1)
            - np.where(expirs_next_expiry, put_charm_ex, 0).sum(axis=1)
        ) / 10**9
        if expir == "all":
            # exposure for next monthly opex
            totaldelta["ex_fri"] = (
                np.where(expirs_up_to_monthly_opex, call_delta_ex, 0).sum(axis=1)
                + np.where(expirs_up_to_monthly_opex, put_delta_ex, 0).sum(axis=1)
            ) / 10**9
            totalgamma["ex_fri"] = (
                np.where(expirs_up_to_monthly_opex, call_gamma_ex, 0).sum(axis=1)
                - np.where(expirs_up_to_monthly_opex, put_gamma_ex, 0).sum(axis=1)
            ) / 10**9
            totalvanna["ex_fri"] = (
                np.where(expirs_up_to_monthly_opex, call_vanna_ex, 0).sum(axis=1)
                - np.where(expirs_up_to_monthly_opex, put_vanna_ex, 0).sum(axis=1)
            ) / 10**9
            totalcharm["ex_fri"] = (
                np.where(expirs_up_to_monthly_opex, call_charm_ex, 0).sum(axis=1)
                - np.where(expirs_up_to_monthly_opex, put_charm_ex, 0).sum(axis=1)
            ) / 10**9

    # Find Delta Flip Point
    zero_cross_idx = np.where(np.diff(np.sign(totaldelta["all"])))[0]
    neg_delta = totaldelta["all"][zero_cross_idx]
    pos_delta = totaldelta["all"][zero_cross_idx + 1]
    neg_strike = levels[zero_cross_idx]
    pos_strike = levels[zero_cross_idx + 1]
    zerodelta = pos_strike - (
        (pos_strike - neg_strike) * pos_delta / (pos_delta - neg_delta)
    )
    # Find Gamma Flip Point
    zero_cross_idx = np.where(np.diff(np.sign(totalgamma["all"])))[0]
    negGamma = totalgamma["all"][zero_cross_idx]
    posGamma = totalgamma["all"][zero_cross_idx + 1]
    neg_strike = levels[zero_cross_idx]
    pos_strike = levels[zero_cross_idx + 1]
    zerogamma = pos_strike - (
        (pos_strike - neg_strike) * posGamma / (posGamma - negGamma)
    )

    if zerodelta.size > 0:
        zerodelta = zerodelta[0][0]
    else:
        zerodelta = 0
        print("delta flip not found for", ticker, expir)
    if zerogamma.size > 0:
        zerogamma = zerogamma[0][0]
    else:
        zerogamma = 0
        print("gamma flip not found for", ticker, expir)

    return (
        option_data,
        today_ddt,
        today_ddt_string,
        monthly_options_dates,
        spot_price,
        from_strike,
        to_strike,
        levels.ravel(),
        totaldelta,
        totalgamma,
        totalvanna,
        totalcharm,
        zerodelta,
        zerogamma,
        call_ivs,
        put_ivs,
    )


def get_options_data_json(ticker, expir, tz):
    try:
        # CBOE file format, json
        with open(
            Path(f"{getcwd()}/data/json/{ticker}_quotedata.json"), encoding="utf-8"
        ) as json_file:
            json_data = json_file.read()
        data = pd.json_normalize(orjson.loads(json_data))
    except orjson.JSONDecodeError as e:  # handle error if data unavailable
        print(f"{e}, {ticker} {expir} data is unavailable")
        return

    # Get Spot
    spot_price = data["data.current_price"][0].astype(float)

    # Get Today's Date
    today_date = DateDataParser(
        settings={
            "TIMEZONE": "UTC",
            "TO_TIMEZONE": tz,
            "RETURN_AS_TIMEZONE_AWARE": True,
        }
    ).get_date_data(str(data["timestamp"][0]))
    # Handle date formats
    today_ddt = today_date.date_obj - timedelta(minutes=15)
    today_ddt_string = today_ddt.strftime("%Y %b %d, %I:%M %p %Z") + " (15min delay)"

    option_data = format_data(
        data["data.options"][0],
        today_ddt,
        today_date.date_obj.tzinfo,
    )

    all_dates = option_data["expiration_date"].drop_duplicates()
    first_expiry = all_dates.iat[0]
    if today_ddt > first_expiry:
        # first date expired so, if available, use next date as 0DTE
        try:
            option_data = option_data[option_data["expiration_date"] != first_expiry]
            first_expiry = all_dates.iat[1]
        except IndexError:
            print("next date unavailable. using expired date")

    next_monthly_opex = get_next_monthly_opex(first_expiry, tz)
    this_monthly_opex, calendar_range = is_third_friday(first_expiry, tz)

    if expir == "monthly":
        option_data = option_data[
            option_data["expiration_date"]
            <= (calendar_range[-1].replace(tzinfo=ZoneInfo(tz)) + timedelta(hours=16))
        ]
    elif expir == "0dte":
        option_data = option_data[option_data["expiration_date"] == first_expiry]
    elif expir == "opex":
        option_data = option_data[option_data["expiration_date"] <= this_monthly_opex]

    return calc_exposures(
        option_data,
        ticker,
        expir,
        first_expiry,
        next_monthly_opex,
        this_monthly_opex,
        spot_price,
        today_ddt,
        today_ddt_string,
    )


def get_options_data_csv(ticker, expir, tz):
    try:
        # CBOE file format, csv
        with open(
            Path(f"{getcwd()}/data/csv/{ticker}_quotedata.csv"), encoding="utf-8"
        ) as csv_file:
            next(csv_file)  # skip first line
            spot_line = csv_file.readline()
            date_line = csv_file.readline()
            # Option data starts at line 4
            option_data = pd.read_csv(
                csv_file,
                header=0,
                names=[
                    "expiration_date",
                    "calls",
                    "call_last_sale",
                    "call_net",
                    "call_bid",
                    "call_ask",
                    "call_vol",
                    "call_iv",
                    "call_delta",
                    "call_gamma",
                    "call_open_int",
                    "strike_price",
                    "puts",
                    "put_last_sale",
                    "put_net",
                    "put_bid",
                    "put_ask",
                    "put_vol",
                    "put_iv",
                    "put_delta",
                    "put_gamma",
                    "put_open_int",
                ],
                usecols=lambda x: x
                not in [
                    "call_last_sale",
                    "call_net",
                    "call_bid",
                    "call_ask",
                    "put_last_sale",
                    "put_net",
                    "put_bid",
                    "put_ask",
                ],
            )
    except:  # handle error if data unavailable
        print(ticker, expir, "data is unavailable")
        return

    # Get Spot
    spot_price = float(spot_line.split("Last:")[1].split(",")[0])

    # Get Today's Date
    today_date = date_line.split("Date: ")[1].split(",Bid")[0]
    # Handle date formats
    if is_parsable(today_date):
        pass
    else:
        tmp = today_date.split()
        tmp[-1], tmp[-2] = tmp[-2], tmp[-1]
        today_date = " ".join(tmp)
    today_date = DateDataParser(settings={"TIMEZONE": tz}).get_date_data(today_date)
    today_ddt = today_date.date_obj - timedelta(minutes=15)
    today_ddt_string = today_ddt.strftime("%Y %b %d, %I:%M %p %Z") + " (15min delay)"

    option_data["expiration_date"] = pd.to_datetime(
        option_data["expiration_date"], format="%a %b %d %Y"
    ).dt.tz_localize(today_date.date_obj.tzinfo) + timedelta(hours=16)
    option_data["strike_price"] = option_data["strike_price"].astype(float)
    option_data["call_iv"] = option_data["call_iv"].astype(float)
    option_data["put_iv"] = option_data["put_iv"].astype(float)
    option_data["call_delta"] = option_data["call_delta"].astype(float)
    option_data["put_delta"] = option_data["put_delta"].astype(float)
    option_data["call_gamma"] = option_data["call_gamma"].astype(float)
    option_data["put_gamma"] = option_data["put_gamma"].astype(float)
    option_data["call_open_int"] = option_data["call_open_int"].astype(float)
    option_data["put_open_int"] = option_data["put_open_int"].astype(float)

    all_dates = option_data["expiration_date"].drop_duplicates()
    first_expiry = all_dates.iat[0]
    if today_ddt > first_expiry:
        # first date expired so, if available, use next date as 0DTE
        try:
            option_data = option_data[option_data["expiration_date"] != first_expiry]
            first_expiry = all_dates.iat[1]
        except IndexError:
            print("next date unavailable. using expired date")
    next_monthly_opex = get_next_monthly_opex(first_expiry, tz)
    this_monthly_opex, calendar_range = is_third_friday(first_expiry, tz)

    busday_counts = np.busday_count(
        today_ddt.date(),
        option_data["expiration_date"].values.astype("datetime64[D]"),
    )
    # set DTE. 0DTE options are included in 1 day expirations
    # time to expiration in years (252 trading days)
    option_data["time_till_exp"] = np.where(
        busday_counts == 0, 1 / 252, busday_counts / 252
    )

    if expir == "monthly":
        option_data = option_data[
            option_data["expiration_date"]
            <= (calendar_range[-1].replace(tzinfo=ZoneInfo(tz)) + timedelta(hours=16))
        ]
    elif expir == "0dte":
        option_data = option_data[option_data["expiration_date"] == first_expiry]
    elif expir == "opex":
        option_data = option_data[option_data["expiration_date"] <= this_monthly_opex]

    return calc_exposures(
        option_data,
        ticker,
        expir,
        first_expiry,
        next_monthly_opex,
        this_monthly_opex,
        spot_price,
        today_ddt,
        today_ddt_string,
    )


def get_options_data(ticker, expir, is_json, tz):
    return (
        get_options_data_json(ticker, expir, tz)
        if is_json
        else get_options_data_csv(ticker, expir, tz)
    )
