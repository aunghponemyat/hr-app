import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { useApi } from '../../api/useApi'
import { errorMessage } from '../../api/errors'
import type { Location } from '../../types/domain'
import { Dialog } from '../../components/Dialog'
import { FormField } from '../../components/FormField'
import { StatusBanner } from '../../components/Feedback'

const coordinate = (limit: number) =>
  z
    .string()
    .regex(/^-?\d+(\.\d{1,6})?$/, 'Use up to six decimal places.')
    .refine(
      (value) =>
        Number.isFinite(Number(value)) && Math.abs(Number(value)) <= limit,
      `Use a value between -${limit} and ${limit}.`,
    )
const schema = z.object({
  name: z.string().trim().min(1, 'A location name is required.').max(100),
  latitude: coordinate(90),
  longitude: coordinate(180),
  allowed_radius_m: z
    .number()
    .int()
    .min(50, 'Use a radius of 50–300 m.')
    .max(300, 'Use a radius of 50–300 m.'),
})
export function LocationEditor({
  location,
  onClose,
}: {
  location: Location | null
  onClose: () => void
}) {
  const api = useApi(),
    client = useQueryClient()
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: location?.name || '',
      latitude: location?.latitude || '',
      longitude: location?.longitude || '',
      allowed_radius_m: location?.allowed_radius_m || 300,
    },
  })
  const save = useMutation({
    mutationFn: (values: z.infer<typeof schema>) =>
      location
        ? api.patch(`/admin/work-locations/${location.id}`, values)
        : api.post('/admin/work-locations', values),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin'] })
      onClose()
    },
  })
  return (
    <Dialog
      title={
        location ? `Edit location · ${location.name}` : 'Create work location'
      }
      onClose={onClose}
      busy={save.isPending}
    >
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => save.mutate(values))}
      >
        <FormField
          id="location-name"
          label="Location name"
          {...form.register('name')}
          error={form.formState.errors.name?.message}
        />
        <FormField
          id="location-lat"
          label="Latitude"
          inputMode="decimal"
          {...form.register('latitude')}
          error={form.formState.errors.latitude?.message}
        />
        <FormField
          id="location-lon"
          label="Longitude"
          inputMode="decimal"
          {...form.register('longitude')}
          error={form.formState.errors.longitude?.message}
        />
        <FormField
          id="location-radius"
          label="Allowed radius (m)"
          type="number"
          min={50}
          max={100}
          step={1}
          {...form.register('allowed_radius_m', { valueAsNumber: true })}
          error={form.formState.errors.allowed_radius_m?.message}
        />
        <StatusBanner
          message={save.error ? errorMessage(save.error) : null}
          error
        />
        <button disabled={save.isPending}>
          {location ? 'Save location' : 'Create location'}
        </button>
      </form>
    </Dialog>
  )
}
