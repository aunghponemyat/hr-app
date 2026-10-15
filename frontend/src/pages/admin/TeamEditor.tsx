import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { useApi } from '../../api/useApi'
import { errorMessage } from '../../api/errors'
import type { Team } from '../../types/domain'
import { Dialog } from '../../components/Dialog'
import { FormField } from '../../components/FormField'
import { TextAreaField } from '../../components/Fields'
import { StatusBanner } from '../../components/Feedback'

const schema = z.object({
  name: z.string().trim().min(1, 'A team name is required.').max(100),
  description: z.string().max(5000),
})
export function TeamEditor({
  team,
  onClose,
}: {
  team: Team | null
  onClose: () => void
}) {
  const api = useApi(),
    client = useQueryClient()
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: team?.name || '',
      description: team?.description || '',
    },
  })
  const save = useMutation({
    mutationFn: (values: z.infer<typeof schema>) => {
      const input = {
        name: values.name,
        description: values.description || null,
      }
      return team
        ? api.patch(`/admin/teams/${team.id}`, input)
        : api.post('/admin/teams', input)
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin'] })
      onClose()
    },
  })
  return (
    <Dialog
      title={team ? `Edit team · ${team.name}` : 'Create team'}
      onClose={onClose}
      busy={save.isPending}
    >
      <form
        noValidate
        onSubmit={form.handleSubmit((values) => save.mutate(values))}
      >
        <FormField
          id="team-name"
          label="Team name"
          {...form.register('name')}
          error={form.formState.errors.name?.message}
        />
        <TextAreaField
          id="team-description"
          label="Description (optional)"
          {...form.register('description')}
          error={form.formState.errors.description?.message}
        />
        <StatusBanner
          message={save.error ? errorMessage(save.error) : null}
          error
        />
        <button disabled={save.isPending}>
          {team ? 'Save team' : 'Create team'}
        </button>
      </form>
    </Dialog>
  )
}
