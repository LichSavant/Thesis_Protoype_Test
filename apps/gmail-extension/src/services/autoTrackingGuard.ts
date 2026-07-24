export class AutoTrackingGuard {
  private lastMessageId: string | null = null;
  shouldTrack(messageId: string): boolean {
    if (messageId === this.lastMessageId) return false;
    this.lastMessageId = messageId;
    return true;
  }
}
