type Handler = ((event: ProgressEvent) => void) | null;

export class MockUploadRequest {
  upload: { onprogress: Handler; onload: Handler } = {
    onprogress: null,
    onload: null,
  };
  onload: Handler = null;
  onabort: Handler = null;
  onerror: Handler = null;
  status = 0;
  response: unknown = null;
  withCredentials = false;
  responseType = "";
  open = jest.fn();
  send = jest.fn();
  setRequestHeader = jest.fn();
  abort = jest.fn(() => this.onabort?.(new ProgressEvent("abort")));
  progress(loaded: number, total?: number) {
    this.upload.onprogress?.(
      new ProgressEvent("progress", {
        loaded,
        total,
        lengthComputable: total !== undefined,
      }),
    );
  }
  transferred(total: number) {
    this.upload.onload?.(
      new ProgressEvent("load", {
        loaded: total,
        total,
        lengthComputable: true,
      }),
    );
  }
  respond(payload: unknown, status = 201) {
    this.status = status;
    this.response = payload;
    this.onload?.(new ProgressEvent("load"));
  }
}

export function mockUploads() {
  const requests: MockUploadRequest[] = [];
  const mock = jest.spyOn(window, "XMLHttpRequest").mockImplementation(() => {
    const request = new MockUploadRequest();
    requests.push(request);
    return request as unknown as XMLHttpRequest;
  });
  return { requests, restore: () => mock.mockRestore() };
}
