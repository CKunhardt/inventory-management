// CSV generation helpers, kept out of the view so the escaping rules are unit-testable.

// RFC 4180: quote a field when it contains a comma, a double quote, CR or LF,
// and double any embedded quote. Without this, a product name like
// "Bracket, 40mm" silently becomes two columns.
export function escapeCsvField(value) {
  if (value === null || value === undefined) return ''
  const str = String(value)
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

// Rows are arrays of primitives already in the order of `headers`.
// CRLF is the line ending RFC 4180 specifies; Excel and Sheets both accept it.
export function toCsv(headers, rows) {
  const lines = [headers.map(escapeCsvField).join(',')]
  for (const row of rows) {
    lines.push(row.map(escapeCsvField).join(','))
  }
  return lines.join('\r\n')
}

// yyyy-mm-dd in local time. toISOString() would shift the date backwards for
// anyone west of UTC late in the day, which puts the wrong date on the file.
export function isoDateStamp(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

// Browser-only. Excel assumes the system codepage unless the file opens with a
// UTF-8 BOM, which mangles the Japanese product names under the ja locale.
export function downloadCsv(filename, csvText) {
  const blob = new Blob(['﻿' + csvText], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
