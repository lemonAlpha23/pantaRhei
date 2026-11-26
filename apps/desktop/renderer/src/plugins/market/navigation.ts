import { useWorkbench } from '../../core/workbench'
import { useWorkspace } from './store'

export const useMarketNavigation = () => {
  const store = useWorkspace()
  const { navigate } = useWorkbench()
  const search = (manage = false) => { store.searchMode = manage ? 'favorites' : 'stock' }
  const openStock = (symbol: string) => {
    store.searchMode = null
    navigate('market')
    if (store.selected !== symbol || !store.history) void store.select(symbol)
  }
  return { search, openStock }
}
