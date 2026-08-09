import { useQuery } from '@tanstack/react-query'
import { activityApi } from '../api/activity'

export function useActivity(enabled: boolean) {
  return useQuery({
    queryKey: ['activity'],
    queryFn: () => activityApi.list(15),
    enabled,
  })
}
