import { describe, it, expect } from 'vitest'
import { escapeCsvField, toCsv, isoDateStamp } from './csv'

describe('escapeCsvField', () => {
  it('leaves plain values alone', () => {
    expect(escapeCsvField('SKU-100')).toBe('SKU-100')
    expect(escapeCsvField(42)).toBe('42')
  })

  it('renders null and undefined as empty, not as the words', () => {
    expect(escapeCsvField(null)).toBe('')
    expect(escapeCsvField(undefined)).toBe('')
  })

  it('keeps zero, which is falsy but a real value', () => {
    expect(escapeCsvField(0)).toBe('0')
  })

  it('quotes a field containing a comma', () => {
    expect(escapeCsvField('Bracket, 40mm')).toBe('"Bracket, 40mm"')
  })

  it('doubles embedded quotes and wraps the field', () => {
    expect(escapeCsvField('12" cable')).toBe('"12"" cable"')
  })

  it('quotes fields containing newlines', () => {
    expect(escapeCsvField('line1\nline2')).toBe('"line1\nline2"')
    expect(escapeCsvField('line1\r\nline2')).toBe('"line1\r\nline2"')
  })

  it('passes multibyte text through unquoted', () => {
    expect(escapeCsvField('圧力センサー')).toBe('圧力センサー')
  })
})

describe('toCsv', () => {
  it('writes a header row followed by CRLF-separated data rows', () => {
    const csv = toCsv(['sku', 'qty'], [['A-1', 5], ['A-2', 7]])
    expect(csv).toBe('sku,qty\r\nA-1,5\r\nA-2,7')
  })

  it('emits only the header when there are no rows', () => {
    expect(toCsv(['sku', 'qty'], [])).toBe('sku,qty')
  })

  it('escapes fields inside rows', () => {
    const csv = toCsv(['name'], [['Bracket, 40mm']])
    expect(csv).toBe('name\r\n"Bracket, 40mm"')
  })

  it('does not emit a trailing newline that would read as a blank row', () => {
    expect(toCsv(['a'], [['b']]).endsWith('\n')).toBe(false)
  })
})

describe('isoDateStamp', () => {
  it('formats as yyyy-mm-dd with zero padding', () => {
    expect(isoDateStamp(new Date(2026, 0, 5))).toBe('2026-01-05')
  })

  // A UTC-based stamp rolls back a day for western timezones late in the
  // evening; local getters are what keep the filename matching the user's date.
  it('uses local date parts rather than UTC', () => {
    const lateEvening = new Date(2026, 8, 17, 23, 30)
    expect(isoDateStamp(lateEvening)).toBe('2026-09-17')
  })
})
