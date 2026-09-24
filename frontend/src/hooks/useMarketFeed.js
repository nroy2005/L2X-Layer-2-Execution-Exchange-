import { useSyncExternalStore } from "react";
import { MarketFeed } from "@/lib/marketFeed";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;
const WS_URL = `${BACKEND_URL.replace(/^http/, "ws")}/api/ws/market-data`;

let feed;

export function getFeed() {
  if (!feed) feed = new MarketFeed(WS_URL);
  return feed;
}

export function useFeedSnapshot() {
  const f = getFeed();
  return useSyncExternalStore(
    (cb) => {
      f.subscribers.add(cb);
      return () => f.subscribers.delete(cb);
    },
    () => f.snapshot,
  );
}
