export function shouldShowRetrievalDebugPage(pathname: string, enabled: boolean): boolean {
  return enabled && pathname === '/debug/retrieval'
}
