/** Keep native send completion from indefinitely owning the receiver queue.
 * Normal protocol replies are retryable by the phone. Releasing their local
 * send wait never acknowledges a file write: the receiver creates that reply
 * only after its durable operation completes. Q must retain native confirmation.
 */
interface SendLink {
  send(options: {
    data: { msg: string; [key: string]: unknown };
    success: () => void;
    fail: (data: unknown, code: number) => void;
  }): void;
}
interface PendingSend {
  progress: () => void;
  cancel: () => void;
}

export class InterconnectSendQueue {
  private readonly pending = new Set<PendingSend>();

  constructor(private readonly allowDispatchProgress: boolean) {}

  peerProgress(packet: string): void {
    // Ignore empty/unknown events. Q responses cannot be released this way.
    if (!/^[HTPFCLQ]/.test(packet)) return;
    Array.from(this.pending).forEach(wait => wait.progress());
  }

  cancel(): void {
    Array.from(this.pending).forEach(wait => wait.cancel());
  }

  send(link: SendLink, envelope: { msg: string; [key: string]: unknown }): Promise<void> {
    const dispatchOnly = this.allowDispatchProgress && envelope.msg[0] !== "Q";
    return new Promise<void>((resolve, reject) => {
      let settled = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        if (timer !== undefined) clearTimeout(timer);
        this.pending.delete(wait);
        if (error) reject(error); else resolve();
      };
      const wait: PendingSend = {
        progress: () => { if (dispatchOnly) finish(); },
        cancel: () => finish(new Error("interconnect 连接已结束"))
      };
      this.pending.add(wait);
      timer = setTimeout(() => {
        if (dispatchOnly) {
          // This means dispatch wait released, NOT native delivery confirmed.
          // The phone still requires the actual H/T/P/A/C response on the wire.
          console.warn("[Corona P65] native send callback missing; release reply wait", envelope.msg[0]);
          finish();
        } else finish(new Error("interconnect.send 完成回调超时"));
      }, dispatchOnly ? 1500 : 2000);
      try {
        link.send({
          data: envelope,
          success: () => finish(),
          fail: (data, code) => finish(new Error(`interconnect.send 失败（${code}）：${String(data)}`))
        });
      } catch (error) { finish(error instanceof Error ? error : new Error(String(error))); }
    });
  }
}
