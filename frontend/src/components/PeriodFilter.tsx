import { useId } from 'react'
import type { Period, PeriodView } from '../utils/dates'
import { periodBounds, rangeError, shiftPeriod } from '../utils/dates'

export function PeriodFilter({
  value,
  onChange,
  years,
  maxDays,
  earliest,
}: {
  value: Period
  onChange: (value: Period) => void
  years: number[]
  maxDays: number
  earliest?: string
}) {
  const id = useId()
  const bounds = periodBounds(value)
  const previous = periodBounds(shiftPeriod(value, -1))
  const error = rangeError(bounds.from, bounds.to, maxDays, earliest)
  return (
    <fieldset className="period-filter">
      <legend>Attendance period</legend>
      <div className="filters">
        <div className="field">
          <label htmlFor={`${id}-view`}>View</label>
          <select
            id={`${id}-view`}
            value={value.view}
            onChange={(event) =>
              onChange({ ...value, view: event.target.value as PeriodView })
            }
          >
            {['week', 'month', 'year', 'custom'].map((view) => (
              <option key={view} value={view}>
                {view[0].toUpperCase() + view.slice(1)}
              </option>
            ))}
          </select>
        </div>
        {value.view === 'custom' ? (
          <>
            <div className="field">
              <label htmlFor={`${id}-from`}>From</label>
              <input
                id={`${id}-from`}
                type="date"
                value={value.from}
                onChange={(event) =>
                  onChange({ ...value, from: event.target.value })
                }
              />
            </div>
            <div className="field">
              <label htmlFor={`${id}-to`}>To</label>
              <input
                id={`${id}-to`}
                type="date"
                value={value.to}
                onChange={(event) =>
                  onChange({ ...value, to: event.target.value })
                }
              />
            </div>
          </>
        ) : (
          <>
            <button
              className="secondary"
              aria-label="Previous period"
              disabled={
                !!rangeError(previous.from, previous.to, maxDays, earliest)
              }
              onClick={() => onChange(shiftPeriod(value, -1))}
            >
              ←
            </button>
            <div className="field">
              <label htmlFor={`${id}-anchor`}>Anchor date</label>
              <input
                type="date"
                id={`${id}-anchor`}
                value={value.anchor}
                onChange={(event) => {
                  if (event.target.value)
                    onChange({ ...value, anchor: event.target.value })
                }}
              />
            </div>
            <button
              className="secondary"
              aria-label="Next period"
              onClick={() => onChange(shiftPeriod(value, 1))}
            >
              →
            </button>
            {years.length > 0 && (
              <div className="field">
                <label htmlFor={`${id}-year`}>Year with records</label>
                <select
                  id={`${id}-year`}
                  value={
                    years.includes(Number(value.anchor.slice(0, 4)))
                      ? value.anchor.slice(0, 4)
                      : ''
                  }
                  onChange={(event) =>
                    onChange({
                      ...value,
                      anchor: `${event.target.value}-01-01`,
                    })
                  }
                >
                  <option value="" disabled>
                    Choose year
                  </option>
                  {years.map((year) => (
                    <option key={year}>{year}</option>
                  ))}
                </select>
              </div>
            )}
          </>
        )}
      </div>
      {error ? (
        <p role="alert" className="field-error">
          {error}
        </p>
      ) : (
        <p className="muted small">
          {bounds.from} — {bounds.to}
        </p>
      )}
    </fieldset>
  )
}
