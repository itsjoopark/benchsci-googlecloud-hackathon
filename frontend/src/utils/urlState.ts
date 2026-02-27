export function getSnapshotIdFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get("snapshot");
}

export function setSnapshotIdInUrl(id: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set("snapshot", id);
  window.history.pushState({}, "", url.toString());
}

export function clearUrlState(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete("snapshot");
  window.history.replaceState({}, "", url.toString());
}
