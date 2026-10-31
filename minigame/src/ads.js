// 激励视频广告。广告位 ID 要在平台后台开通“流量主”后才拿得到，填进 data/ads.json；
// 没填的时候 adsEnabled() 为 false，游戏里不会出现任何“看广告”按钮。
import ads from "../build/data/ads.json";
import { PLATFORM } from "./platform.js";
import { floatText, C } from "./ui.js";

const api = typeof wx !== "undefined" ? wx : typeof tt !== "undefined" ? tt : null;
const unitId = () => (ads[PLATFORM] || {}).rewarded || "";

export function adsEnabled() { return !!(api && api.createRewardedVideoAd && unitId()); }

let ad = null, pending = null;
function getAd() {
  if (ad) return ad;
  ad = api.createRewardedVideoAd({ adUnitId: unitId() });
  ad.onClose((res) => {
    const done = !res || res.isEnded;   // 看完才给奖励
    const fn = pending; pending = null;
    if (done && fn) fn(); else if (fn) floatText("没看完，奖励没拿到", C.muted);
  });
  ad.onError(() => { pending = null; });
  return ad;
}

/** 播放激励视频；看完后调用 onReward。placement 只用来区分用途。 */
export function showRewardedAd(placement, onReward) {
  if (!adsEnabled()) return;
  const a = getAd();
  pending = onReward;
  a.show().catch(() => a.load().then(() => a.show()).catch(() => { pending = null; floatText("广告暂时没准备好", C.muted); }));
}
