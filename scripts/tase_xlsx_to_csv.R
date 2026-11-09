# Convert the 2016 TASE general index workbook to a plain CSV.
#
# The workbook has one row per month from 1979-12 to 2016-08 (the month column
# is written as "m.yy", the year only every January). Column 5 is the nominal
# general share index (a price index, without dividends); it is complete from
# 1993-12.
#
# Run from the repo root:  Rscript scripts/tase_xlsx_to_csv.R

suppressMessages(library(readxl))
raw <- suppressMessages(read_excel("data/raw/tase_general_index_1979_2016.xlsx", col_names = FALSE, col_types = "text"))[-(1:2), ]
months <- seq(as.Date("1979-12-01"), by = "month", length.out = nrow(raw))
stopifnot(format(tail(months, 1), "%Y-%m") == "2016-08")
out <- data.frame(month = format(months, "%Y-%m"), tase_index = as.numeric(raw[[5]]))
out <- out[!is.na(out$tase_index) & out$month >= "1993-12", ]
stopifnot(all(diff(as.Date(paste0(out$month, "-01"))) <= 31))
write.csv(out, "data/raw/tase_general_index_1993_2016.csv", row.names = FALSE)
cat("Wrote", nrow(out), "months,", out$month[1], "to", tail(out$month, 1), "\n")
