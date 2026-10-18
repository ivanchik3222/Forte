import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEvidencePlayback } from "./useEvidencePlayback";
import { intervalTime } from "./playback";

function Harness() {
  const playback = useEvidencePlayback();
  return <><section ref={playback.panel} tabIndex={-1} aria-label="Player"><video data-testid="video" ref={playback.video}
    onLoadedMetadata={playback.onLoadedMetadata} onTimeUpdate={playback.onTimeUpdate} onSeeking={playback.onSeeking} onPlay={playback.onPlay} />
    {playback.range && <p>Selected interval</p>}{playback.playBlocked && <p>Press play</p>}</section>
    <button onClick={() => playback.seek(7.1, { start: 7.1, end: 7.8, label: "Cash" })}>Interval</button>
    <button onClick={playback.clearRange}>Full video</button></>;
}
const scroll = jest.fn();
const originalScroll = HTMLElement.prototype.scrollIntoView;
let play: jest.SpyInstance, pause: jest.SpyInstance;
beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = scroll; scroll.mockReset();
  play = jest.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  pause = jest.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
});
afterEach(() => { play.mockRestore(); pause.mockRestore(); HTMLElement.prototype.scrollIntoView = originalScroll; });
const prepare = (ready = 1, duration = 30) => {
  render(<Harness />);
  const video = screen.getByTestId("video") as HTMLVideoElement;
  Object.defineProperties(video, { readyState: { configurable: true, value: ready }, duration: { configurable: true, value: duration }, paused: { value: false } });
  return video;
};

test("interval seeks precisely, focuses the player and stops at its end", () => {
  const video = prepare();
  fireEvent.click(screen.getByText("Interval"));
  expect(video.currentTime).toBe(7.1);
  expect(play).toHaveBeenCalled();
  expect(scroll).toHaveBeenCalledWith({ block: "start", behavior: "smooth" });
  expect(screen.getByRole("region", { name: "Player" })).toHaveFocus();
  video.currentTime = 8; fireEvent.timeUpdate(video);
  expect(pause).toHaveBeenCalled(); expect(video.currentTime).toBe(7.8);
  fireEvent.click(screen.getByText("Full video"));
  pause.mockClear(); video.currentTime = 9; fireEvent.timeUpdate(video);
  expect(pause).not.toHaveBeenCalled();
  expect(intervalTime(7.1, 7.8)).toBe("00:07.1–00:07.8");
});

test("selection survives pending metadata; manual seeking releases the interval", async () => {
  const video = prepare(0);
  play.mockRejectedValueOnce(new Error("Autoplay blocked"));
  fireEvent.click(screen.getByText("Interval"));
  expect(play).not.toHaveBeenCalled();
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(7.1);
  await waitFor(() => expect(screen.getByText("Press play")).toBeVisible());
  video.currentTime = 20; fireEvent.seeking(video);
  expect(screen.queryByText("Selected interval")).not.toBeInTheDocument();
});

test("a shorter source video cannot produce a reversed playback interval", () => {
  const video = prepare(0, NaN);
  fireEvent.click(screen.getByText("Interval"));
  expect(screen.getByText("Selected interval")).toBeVisible();
  Object.defineProperty(video, "duration", { value: 5 });
  fireEvent.loadedMetadata(video);
  expect(video.currentTime).toBe(5);
  expect(screen.queryByText("Selected interval")).not.toBeInTheDocument();
});
