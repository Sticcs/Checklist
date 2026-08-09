import { useQuery, useQueryClient } from '@tanstack/react-query'
import { statsApi } from '../api/stats'

export const STATS_KEY = ['stats']

export function useStats(enabled: boolean) {
  return useQuery({ queryKey: STATS_KEY, queryFn: statsApi.get, enabled })
}

export function useInvalidateStats() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: STATS_KEY })
}
