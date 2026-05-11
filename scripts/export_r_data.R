#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(arrow)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
source_dir <- if (length(args) >= 1) args[[1]] else "/Users/hovav/Documents/R projects/Invest"
output_dir <- if (length(args) >= 2) args[[2]] else "data"
metadata_path <- if (length(args) >= 3) args[[3]] else "tests/fixtures/r_outputs/metadata.json"

source_rda <- file.path(source_dir, "Invest.rda")
if (!file.exists(source_rda)) {
  stop("Invest.rda not found at: ", source_rda, call. = FALSE)
}
if (!file.exists(metadata_path)) {
  stop("Phase 1 metadata not found at: ", metadata_path, call. = FALSE)
}

metadata <- jsonlite::read_json(metadata_path, simplifyVector = FALSE)
objects <- names(metadata$objects)

loaded <- new.env(parent = emptyenv())
load(source_rda, envir = loaded)
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

manifest_objects <- list()

validate_object <- function(name, data, expected) {
  if (!is.data.frame(data)) {
    stop(name, " is not a data frame", call. = FALSE)
  }

  expected_rows <- as.integer(expected$rows)
  expected_columns <- as.integer(expected$columns)
  actual_dim <- dim(data)
  if (!identical(actual_dim, c(expected_rows, expected_columns))) {
    stop(
      name, " shape mismatch: expected ",
      expected_rows, " x ", expected_columns,
      ", got ", actual_dim[[1]], " x ", actual_dim[[2]],
      call. = FALSE
    )
  }

  expected_names <- unlist(expected$names, use.names = FALSE)
  if (!identical(names(data), expected_names)) {
    stop(name, " column names do not match Phase 1 metadata", call. = FALSE)
  }

  if (!is.null(expected$date_range)) {
    if (!("date" %in% names(data)) || !inherits(data$date, "Date")) {
      stop(name, " must have a Date column named date", call. = FALSE)
    }
    actual_range <- as.character(range(data$date, na.rm = TRUE))
    expected_range <- unlist(expected$date_range, use.names = FALSE)
    if (!identical(actual_range, expected_range)) {
      stop(
        name, " date range mismatch: expected ",
        paste(expected_range, collapse = " to "),
        ", got ", paste(actual_range, collapse = " to "),
        call. = FALSE
      )
    }
  }
}

for (name in objects) {
  if (!exists(name, envir = loaded, inherits = FALSE)) {
    stop("Object missing from Invest.rda: ", name, call. = FALSE)
  }

  data <- get(name, envir = loaded, inherits = FALSE)
  validate_object(name, data, metadata$objects[[name]])

  file_name <- paste0(name, ".parquet")
  output_path <- file.path(output_dir, file_name)
  arrow::write_parquet(data, output_path)

  date_range <- NULL
  if ("date" %in% names(data) && inherits(data$date, "Date")) {
    date_range <- as.character(range(data$date, na.rm = TRUE))
  }

  manifest_objects[[name]] <- list(
    file = file_name,
    rows = unname(nrow(data)),
    columns = unname(ncol(data)),
    names = names(data),
    classes = lapply(data, function(column) class(column)),
    date_range = date_range
  )
}

manifest <- list(
  generated_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
  source_rda = source_rda,
  metadata_reference = metadata_path,
  fixture_version = metadata$fixture_version,
  format = "parquet",
  objects = manifest_objects
)

jsonlite::write_json(
  manifest,
  path = file.path(output_dir, "manifest.json"),
  pretty = TRUE,
  auto_unbox = TRUE,
  null = "null"
)

cat("Exported server data to ", normalizePath(output_dir), "\n", sep = "")
