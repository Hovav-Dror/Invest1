#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(tidyverse)
  library(lubridate)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
source_dir <- if (length(args) >= 1) args[[1]] else "/Users/hovav/Documents/R projects/Invest"
output_dir <- if (length(args) >= 2) args[[2]] else "tests/fixtures/r_outputs"

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
load(file.path(source_dir, "Invest.rda"))

fixture_version <- format(Sys.Date(), "%Y-%m-%d")

write_fixture <- function(name, data) {
  data <- data %>%
    mutate(across(where(is.Date), as.character))

  write_csv(data, file.path(output_dir, paste0(name, ".csv")), na = "")
}

write_json <- function(name, data) {
  jsonlite::write_json(
    data,
    path = file.path(output_dir, paste0(name, ".json")),
    dataframe = "rows",
    pretty = TRUE,
    auto_unbox = TRUE,
    na = "null"
  )
}

tax_events <- function(date1 = as.Date("1993-01-01"), date2 = as.Date("2023-01-01"), adjust_cpi = TRUE) {
  db <- SP500DIV %>%
    select(date, v = SP500wDividends, CPI) %>%
    filter(date >= date1, date <= date2) %>%
    arrange(date) %>%
    mutate(CPI = CPI / first(CPI), v = v / CPI) %>%
    mutate(v = v / first(v), Gain_i = v / lag(v)) %>%
    mutate(End25 = v - (v - 1) * 0.25) %>%
    mutate(EveryMonth = 1, EveryNMonths = 1, Every12Months = 1)

  db$Gain <- 1
  for (i in 2:nrow(db)) {
    tax <- 0.25
    relative <- db$v[i] / db$v[i - 1]

    if (relative <= 1) {
      db$EveryMonth[i] <- db$EveryMonth[i - 1] * relative
    } else {
      gain <- relative - (relative - 1) * tax
      db$Gain[i] <- gain
      db$EveryMonth[i] <- db$EveryMonth[i - 1] * gain
    }

    n <- 6
    db$EveryNMonths[i] <- db$EveryNMonths[i - 1] * db$Gain_i[i]
    if ((i >= (n + 1)) && ((i + 1) %% n == 0)) {
      gain <- db$EveryNMonths[i] - db$EveryNMonths[i - n]
      if (gain > 0) db$EveryNMonths[i] <- db$EveryNMonths[i] - 0.25 * gain
    }

    n <- 12
    db$Every12Months[i] <- db$Every12Months[i - 1] * db$Gain_i[i]
    if ((i >= (n + 1)) && ((i + 1) %% n == 0)) {
      gain <- db$Every12Months[i] - db$Every12Months[i - n]
      if (gain > 0) db$Every12Months[i] <- db$Every12Months[i] - 0.25 * gain
    }
  }

  if (!adjust_cpi) db <- db %>% mutate(across(-date, ~ . * CPI))
  db %>% select(-CPI)
}

commission_tax <- function(commission, date1 = as.Date("1993-01-01"), date2 = as.Date("2023-01-01"), adjust_cpi = TRUE) {
  db <- SP500DIV %>%
    select(date, v = SP500wDividends, CPI) %>%
    filter(date >= date1, date <= date2) %>%
    mutate(CPI = CPI / first(CPI), v = v / CPI) %>%
    mutate(v0 = v) %>%
    arrange(date) %>%
    mutate(v = v / first(v), Gain_i = v / lag(v)) %>%
    mutate(End25 = v - (v - 1) * 0.25) %>%
    mutate(EveryMonth = 1, EveryNMonths = 1, Every12Months = 1)

  db$Gain <- 1
  monthly_commission <- (1 + commission / 100)^(1 / 12) - 1
  for (i in 2:nrow(db)) {
    relative <- db$v0[i] / db$v0[i - 1]
    db$v[i] <- db$v[i - 1] * (1 - monthly_commission) * relative

    if (relative <= 1) {
      db$EveryMonth[i] <- db$EveryMonth[i - 1] * relative * (1 - monthly_commission)
    } else {
      gain <- relative - (relative - 1) * 0.25
      db$Gain[i] <- gain
      db$EveryMonth[i] <- db$EveryMonth[i - 1] * gain * (1 - monthly_commission)
    }

    n <- 6
    db$EveryNMonths[i] <- db$EveryNMonths[i - 1] * db$Gain_i[i] * (1 - monthly_commission)
    if ((i >= (n + 1)) && ((i + 1) %% n == 0)) {
      gain <- db$EveryNMonths[i] - db$EveryNMonths[i - n]
      if (gain > 0) db$EveryNMonths[i] <- db$EveryNMonths[i] * (1 - monthly_commission) - 0.25 * gain
    }

    n <- 12
    db$Every12Months[i] <- db$Every12Months[i - 1] * db$Gain_i[i] * (1 - monthly_commission)
    if ((i >= (n + 1)) && ((i + 1) %% n == 0)) {
      gain <- db$Every12Months[i] - db$Every12Months[i - n]
      if (gain > 0) db$Every12Months[i] <- db$Every12Months[i] * (1 - monthly_commission) - 0.25 * gain
    }
  }

  db <- db %>%
    mutate(End25 = v - (v - 1) * 0.25) %>%
    select(-contains("Gain"), -v) %>%
    rename(
      SP500_in_NIS = v0,
      tax_at_end = End25,
      tax_every_6_months = EveryNMonths,
      tax_every_12_months = Every12Months,
      tax_every_month = EveryMonth
    )

  if (!adjust_cpi) db <- db %>% mutate(across(-date, ~ . * CPI))
  db %>% select(-CPI) %>% mutate(commission = commission)
}

sp500_risk <- function(years = 15, threshold = 0.04) {
  period <- years * 12
  SP500US %>%
    arrange(date) %>%
    mutate(TotalReturn = Real_Total_Return_Price / lag(Real_Total_Return_Price, as.integer(period))) %>%
    drop_na(TotalReturn) %>%
    mutate(TotalReturnP = (TotalReturn^(1 / period))^12 - 1) %>%
    mutate(
      Median = median(TotalReturnP),
      Above0 = sum(TotalReturnP > 0) / n(),
      AboveThreshold = sum(TotalReturnP > threshold) / n()
    ) %>%
    select(date, TotalReturn, TotalReturnP, Median, Above0, AboveThreshold)
}

kupat_gemel <- function(with_pension = FALSE) {
  age1 <- 40
  year1 <- 1995
  initial <- 70000
  pension_months <- 250
  db <- SP500DIV %>%
    select(date, v = SP500wDividends, CPI) %>%
    mutate(year = year(date)) %>%
    filter(year >= year1) %>%
    mutate(year3 = year + (month(date) - 1) / 12, age = year3 - year1 + age1) %>%
    arrange(date) %>%
    mutate(CPI = CPI / first(CPI), MG = replace_na(v / lag(v) - 1, 0)) %>%
    mutate(
      KH = cumprod((1 + MG) * ((1 - 0.65 / 100)^(1 / 12))),
      KH = case_when(KH / CPI <= 1 ~ KH, age < 60 ~ (KH / CPI - (KH / CPI - 1) * 0.25) * CPI, TRUE ~ KH),
      KH60 = sum(KH * (age == 60)),
      CPI60 = sum(CPI * (age == 60)),
      Kitzba = ifelse(age > 60, (KH60 / pension_months) * (CPI / CPI60), 0),
      KH = ifelse(age > 60, KH60 * CPI / CPI60, KH),
      PH = cumprod((1 + MG) * ((1 - 0.75 / 100)^(1 / 12))),
      PH = case_when(PH / CPI <= 1 ~ PH, age < 60 ~ (PH / CPI - (PH / CPI - 1) * 0.25) * CPI, TRUE ~ (PH / CPI - (PH / CPI - 1) * 0.25) * CPI),
      II = (1 - 0.07 / 100) * cumprod((1 + MG) * ((1 - 0.07 / 100)^(1 / 12))),
      II = case_when(II / CPI <= 1 ~ II, TRUE ~ (II / CPI - (II / CPI - 1) * 0.25) * CPI),
      II = II * (1 - 0.07 / 100)
    )

  if (with_pension) {
    db$IIb <- (1 - 0.07 / 100)
    for (i in 2:nrow(db)) {
      db$IIb[i] <- db$IIb[i - 1] * (1 + db$MG[i]) * ((1 - 0.07 / 100)^(1 / 12))
      tax_i <- db$IIb[i] / db$CPI[i]
      tax_i <- ifelse(tax_i <= 1, 1, (tax_i - (tax_i - 1) * 0.25) / tax_i)
      db$IIb[i] <- db$IIb[i] - db$Kitzba[i] / tax_i
    }
    db <- db %>%
      mutate(
        IIb = IIb * (1 - 0.07 / 100),
        IIb = case_when(IIb / CPI <= 1 ~ IIb, TRUE ~ (IIb / CPI - (IIb / CPI - 1) * 0.25) * CPI)
      )
  }

  cols <- if (with_pension) c("KH", "II", "IIb", "Kitzba") else c("KH", "PH", "II")
  db %>%
    mutate(across(all_of(cols), ~ . * first(CPI) / CPI * initial)) %>%
    select(date, age, year3, all_of(cols))
}

independent_commissions <- function(tax_mode = c("optional_tax", "us_vs_il")) {
  tax_mode <- match.arg(tax_mode)
  db1 <- SP500DIV %>%
    select(date, value = SP500wDividends, CPI) %>%
    filter(date >= as.Date("2000-01-01"), date <= as.Date("2023-01-01")) %>%
    left_join(SP500DIV %>% select(date, USD = dollar), by = "date") %>%
    left_join(SP500US %>% select(date, CPI_US), by = "date") %>%
    arrange(date)

  initial <- 100000
  share_price <- 50
  dollar_commission <- 0.005
  commission_per_share <- 0.01
  min_dollar_commission <- 7.5
  yearly_commission <- 0.003
  monthly_commission <- (1 - yearly_commission)^(1 / 12)
  dollar <- db1$USD[1]
  buy_sell_price <- max(c(min_dollar_commission * dollar, (initial / dollar / share_price) * commission_per_share * dollar))

  db2 <- db1 %>%
    mutate(value = value / first(value), firstUSD = first(USD)) %>%
    mutate(across(contains("CPI"), ~ . / first(.))) %>%
    mutate(delta = replace_na(value / lag(value) - 1, 0)) %>%
    mutate(v0 = value * initial, AfterBuying = initial * (1 - dollar_commission) - buy_sell_price)

  db2$v <- accumulate(2:nrow(db2), ~ .x * (1 + db2$delta[.y]) * monthly_commission, .init = db2$AfterBuying[1])

  db2 <- db2 %>%
    rowwise() %>%
    mutate(
      Profit = v / CPI - initial,
      TaxIL = max(c(0.25 * Profit, 0)),
      ProfitNominal = v - initial,
      TaxILNominal = max(c(0.25 * ProfitNominal, 0)),
      vDollar = v / USD,
      ProfitUS = (vDollar - initial / firstUSD) * (firstUSD / USD),
      TaxDollar = min(c(max(c(0.25 * ProfitUS, 0)) * USD, TaxILNominal)),
      BuySellPrice_i = max(c(vDollar / share_price * commission_per_share * USD, min_dollar_commission * USD)),
      v_final = v * (1 - dollar_commission) - ifelse(tax_mode == "optional_tax", 0, TaxIL) - BuySellPrice_i,
      v_finalDollar = v * (1 - dollar_commission) - TaxDollar - BuySellPrice_i
    ) %>%
    ungroup %>%
    mutate(across(c(v0, v_final, v_finalDollar), ~ . * first(CPI) / CPI))

  if (tax_mode == "optional_tax") {
    db2 %>% select(date, v0, v_final)
  } else {
    db2 %>% select(date, v0, v_final_il = v_final, v_final_dollar = v_finalDollar)
  }
}

portfolio_table <- function() {
  selected <- c(
    "S&P 500", "MSCI World ex USA index", "US Large Cap Value", "US Large Cap Growth",
    "US Mid Cap Value", "US Small Cap Value", "Short Term Treasury", "Precious Metals",
    "European Stocks", "Bogleheads Three Funds", "Bill Bernstein No Brainer",
    "Growth Portfolio", "Conservative Portfolio", "Bill Schultheis Coffee house",
    "Emerging Markets", "David Swensen Lazy", "David Swensen Yale Endowment",
    "Ray Dalio All Seasons", "~Ben Felix five-factor model portfolio", "השילוש הקדוש"
  )

  LazyReturns1 %>%
    filter(CommissionUse == TRUE, Portfolio %in% selected, Year >= 1954, Year <= 2023) %>%
    filter(Year >= min(Year[!is.na(Index_CPI_IL)])) %>%
    mutate(v = Index_CPI_IL, ShefelYears = BadYears_CPI_IL, Drop = Drop_CPI_IL) %>%
    group_by(Portfolio) %>%
    arrange(Year) %>%
    mutate(v = v / first(na.omit(v))) %>%
    slice(-1) %>%
    ungroup
}

portfolio_summary <- function() {
  portfolio_table() %>%
    select(Year, Portfolio, v, ShefelYears, Drop) %>%
    group_by(Portfolio) %>%
    arrange(Year) %>%
    summarise(
      FirstYear = first(Year),
      N = n(),
      SD = sd(v / lag(v) - 1, na.rm = TRUE),
      CAGR = last(v)^(1 / N) - 1,
      MaxDrop = min(Drop),
      MaxShefelYears = max(ShefelYears),
      Factor15 = (1 + CAGR)^15,
      .groups = "drop"
    )
}

portfolio_over_time <- function() {
  portfolio_table() %>%
    select(Year, Portfolio, v, ShefelYears, Drop) %>%
    group_by(Portfolio) %>%
    mutate(
      N = max(Year) - first(Year),
      OneYear = v / lag(v) - 1,
      CAGR = v^(1 / N) - 1,
      CAGR10 = (v / lag(v, 10))^(1 / 10) - 1
    ) %>%
    ungroup
}

us_global_rolling <- function(global_mix = FALSE) {
  db <- LazyReturns1 %>%
    filter(!CommissionUse) %>%
    select(Year, Portfolio, YearReturn) %>%
    filter(Portfolio %in% c("S&P 500", "MSCI World ex USA index")) %>%
    group_by(Year) %>%
    filter(n() == 2) %>%
    drop_na() %>%
    ungroup

  if (global_mix) {
    db <- db %>%
      pivot_wider(names_from = Portfolio, values_from = YearReturn) %>%
      mutate(Mix = 0.6 * `S&P 500` + 0.4 * `MSCI World ex USA index`) %>%
      select(Year, `S&P 500`, Mix) %>%
      pivot_longer(-Year, names_to = "Portfolio", values_to = "YearReturn")
    compare_to <- "Mix"
  } else {
    compare_to <- "MSCI World ex USA index"
  }

  db %>%
    group_by(Portfolio) %>%
    arrange(Year) %>%
    mutate(Five2 = cumprod(1 + YearReturn / 100), Five = (Five2 / lag(Five2, 5))^(1 / 5), Ten = (Five2 / lag(Five2, 10))^(1 / 10), Fifteen = (Five2 / lag(Five2, 15))^(1 / 15)) %>%
    drop_na(Five) %>%
    group_by(Year) %>%
    mutate(Diff5 = sum(Five * (Portfolio == "S&P 500"), na.rm = TRUE) - sum(Five * (Portfolio == compare_to), na.rm = TRUE)) %>%
    mutate(Diff10 = sum(Ten * (Portfolio == "S&P 500"), na.rm = TRUE) - sum(Ten * (Portfolio == compare_to), na.rm = TRUE)) %>%
    mutate(Diff15 = sum(Fifteen * (Portfolio == "S&P 500"), na.rm = TRUE) - sum(Fifteen * (Portfolio == compare_to), na.rm = TRUE)) %>%
    filter(Portfolio == "S&P 500") %>%
    select(Year, Diff5, Diff10, Diff15)
}

sp500_scv_rolling <- function(window = 15, after_tax = FALSE) {
  db <- LazyReturns1 %>%
    filter(!CommissionUse, Portfolio %in% c("S&P 500", "US Small Cap Value")) %>%
    filter(Year >= min(Year[!is.na(Index_CPI_IL)])) %>%
    filter(Year >= 1969 - window, Year <= 2023) %>%
    select(Year, Portfolio, CPI_IL, USD, YearReturn, index)

  if (!after_tax) {
    return(db %>%
      mutate(v = index * USD / CPI_IL) %>%
      group_by(Portfolio) %>%
      arrange(Year) %>%
      mutate(CAGR = (v / lag(v, window))^(1 / window) - 1) %>%
      ungroup %>%
      filter(Year >= 1969) %>%
      select(Year, Portfolio, CAGR))
  }

  db %>%
    group_by(Portfolio) %>%
    arrange(Year) %>%
    mutate(
      A8 = 1,
      B8 = A8 / lag(USD, window),
      D8 = index / lag(index, window),
      E8 = CPI_IL / lag(CPI_IL, window),
      F8 = USD / lag(USD, window),
      H8 = D8 * F8 * A8,
      I8 = D8 * B8,
      K8 = H8 - A8,
      BeforeTaxProfitPercent = H8 / A8 / E8 - 1,
      L8 = H8 / E8 - A8,
      U8a = 0.25 * (I8 - B8) * A8 / B8 * F8,
      U8b = 0.25 * K8,
      T8 = pmax(0.25 * L8, 0),
      U8 = pmax(pmin(U8a, U8b), 0),
      TaxPaidShekel = ifelse(Portfolio == "S&P 500", T8, U8),
      NominalReturnAfterTax = H8 - TaxPaidShekel,
      GainAfterTax = (NominalReturnAfterTax / A8) / E8 - 1,
      CAGR_after_tax = (GainAfterTax + 1)^(1 / window) - 1
    ) %>%
    ungroup %>%
    drop_na(CAGR_after_tax) %>%
    filter(Year >= 1969) %>%
    select(Year, Portfolio, GainAfterTax, CAGR_after_tax)
}

sp500_scv_heatmap <- function(max_years = 20) {
  db <- LazyReturns1 %>%
    filter(!CommissionUse, Portfolio %in% c("S&P 500", "US Small Cap Value")) %>%
    filter(Year >= min(Year[!is.na(Index_CPI_IL)])) %>%
    mutate(v = index * USD / CPI_IL) %>%
    select(Portfolio, Year, v) %>%
    group_by(Portfolio) %>%
    arrange(Portfolio, Year)

  for (iy in 1:max_years) {
    db <- db %>% mutate("{iy}" := lag(v, iy))
  }

  db %>%
    ungroup %>%
    mutate(across(-c(Portfolio, Year, v), ~ v / . - 1)) %>%
    select(-v) %>%
    pivot_longer(-c(Portfolio, Year), values_drop_na = TRUE, names_to = "InvYears") %>%
    mutate(InvYears = as.numeric(InvYears), EndYear = Year, StartYear = EndYear - InvYears + 1, CAGR = (value + 1)^(1 / InvYears) - 1) %>%
    group_by(StartYear, EndYear) %>%
    arrange(Portfolio) %>%
    mutate(val1 = first(value), val2 = last(value), cagr1 = first(CAGR), cagr2 = last(CAGR), Portfolio2 = last(Portfolio)) %>%
    slice(1) %>%
    ungroup %>%
    mutate(delta_value = val2 - val1, delta_cagr = cagr2 - cagr1) %>%
    select(StartYear, EndYear, InvYears, Portfolio, Portfolio2, val1, val2, cagr1, cagr2, delta_value, delta_cagr)
}

trinity <- function() {
  trinity_one <- function(portfolio_i, yearly_draw_p, years, year0, base) {
    LazyReturns1 %>%
      filter(Portfolio == portfolio_i, !CommissionUse) %>%
      select(Year, Portfolio, commission, CPI_US, YearReturn) %>%
      filter(Year >= year0, Year <= year0 + years) %>%
      mutate(
        Left = accumulate(
          2:n(),
          .init = base,
          ~ (.x - base * yearly_draw_p) * (.x > 0) * (1 - commission[.y] / 100) * (CPI_US[.y - 1] / CPI_US[.y]) * (1 + YearReturn[.y] / 100) +
            (.x - base * yearly_draw_p) * (.x <= 0) * (CPI_US[.y - 1] / CPI_US[.y])
        )
      ) %>%
      summarise(Investment_remained = last(Left), Investment_low = min(Left[-1]))
  }

  portfolio_i <- "US Small Cap Value"
  years <- 30
  year_range <- LazyReturns1 %>%
    filter(Portfolio == portfolio_i, !CommissionUse) %>%
    filter(Year >= min(Year), Year <= max(Year) - years) %>%
    pull(Year) %>%
    range()

  map_dfr(seq(year_range[1], year_range[2]), function(year_i) {
    trinity_one(portfolio_i, 0.04, years, year_i, 4000000) %>%
      mutate(start_year = year_i, end_year = year_i + years, .before = 1)
  })
}

metadata <- list(
  fixture_version = fixture_version,
  source_dir = source_dir,
  source_git_head = tryCatch(system2("git", c("-C", shQuote(source_dir), "rev-parse", "--short", "HEAD"), stdout = TRUE), error = function(e) NA),
  source_git_status = tryCatch(system2("git", c("-C", shQuote(source_dir), "status", "--short"), stdout = TRUE), error = function(e) character()),
  objects = list(
    LazyReturns1 = list(rows = nrow(LazyReturns1), columns = ncol(LazyReturns1), names = names(LazyReturns1)),
    PortfoliosStructure = list(rows = nrow(PortfoliosStructure), columns = ncol(PortfoliosStructure), names = names(PortfoliosStructure)),
    SP500DIV = list(rows = nrow(SP500DIV), columns = ncol(SP500DIV), names = names(SP500DIV), date_range = as.character(range(SP500DIV$date))),
    SP500US = list(rows = nrow(SP500US), columns = ncol(SP500US), names = names(SP500US), date_range = as.character(range(SP500US$date))),
    US_Small_Cap_Value_Monthly = list(rows = nrow(US_Small_Cap_Value_Monthly), columns = ncol(US_Small_Cap_Value_Monthly), names = names(US_Small_Cap_Value_Monthly), date_range = as.character(range(US_Small_Cap_Value_Monthly$date)))
  ),
  defaults = list(
    tax_dates = c("1993-01-01", "2023-01-01"),
    portfolio_cpi = "המרה לשקלים ומדד ישראל",
    portfolio_years = c(1955, 2023),
    trinity_portfolio = "US Small Cap Value"
  )
)

write_json("metadata", metadata)
write_fixture("tax_events_default", tax_events())
write_fixture("tax_events_no_cpi", tax_events(adjust_cpi = FALSE))
write_fixture("commission_effect_default", bind_rows(commission_tax(0), commission_tax(0.2), commission_tax(0.7)))
write_fixture("commission_tax_default", bind_rows(commission_tax(0), commission_tax(0.2), commission_tax(0.7)))
write_fixture("sp500_risk_default", sp500_risk())
write_fixture("kupat_gemel_default", kupat_gemel(FALSE))
write_fixture("kupat_gemel_pension_default", kupat_gemel(TRUE))
write_fixture("independent_commissions_default", independent_commissions("optional_tax"))
write_fixture("tax_us_vs_il_default", independent_commissions("us_vs_il"))
write_fixture("portfolio_summary_default", portfolio_summary())
write_fixture("portfolio_over_time_default", portfolio_over_time())
write_fixture("us_world_rolling_default", us_global_rolling(FALSE))
write_fixture("us_global_rolling_default", us_global_rolling(TRUE))
write_fixture("sp500_scv_rolling_default", sp500_scv_rolling())
write_fixture("sp500_scv_heatmap_default", sp500_scv_heatmap())
write_fixture("sp500_scv_after_tax_default", sp500_scv_rolling(after_tax = TRUE))
write_fixture("trinity_default", trinity())

message("Exported R fixtures to ", normalizePath(output_dir))
