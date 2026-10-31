// 一笔交易的全部规则（从电脑版 src/deal.gd 原样移植）：顾客性格、货物真实价值、鉴定、质疑来历、砍价。
// 数值来自 data/tuning.json，台词来自 data/personalities.json。

export const rand = (a, b) => a + Math.random() * (b - a);
export const randi = (a, b) => Math.floor(rand(a, b + 1));
export const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const round10 = (v) => Math.max(10, Math.round(v / 10) * 10);

function pickWeighted(rows) {
  const total = rows.reduce((s, r) => s + Number(r[2]), 0);
  let roll = Math.random() * total;
  for (const r of rows) { roll -= Number(r[2]); if (roll <= 0) return r; }
  return rows[0];
}
const meanMult = (variants) => Math.max(0.1, variants.reduce((s, v) => s + Number(v[1]), 0) / Math.max(1, variants.length));

export class Deal {
  constructor(tuning, catalog, archetypes, personas, reputation) {
    this.tuning = tuning;
    const arch = pick(archetypes);
    this.customer = { name: pick(arch.names), type: arch.type, art: arch.art };
    this.persona = personas[this.customer.type];
    this.item = this.makeItem(catalog);
    this.challengeCount = 0;
    this.exposed = false;

    const lieChance = tuning.lie_chance * this.persona.lie_mult - reputation * tuning.rep_lie_reduction;
    this.lying = Math.random() < Math.min(0.9, Math.max(0, lieChance));
    const cat = catalog.categories[this.item.tag];
    const lie = this.lying ? pick(cat.lies) : null;
    if (this.lying) this.story = lie.story;
    else if (Math.random() < 0.45) this.story = pick(catalog.meme_stories);
    else this.story = pick(cat.stories);

    // 抽 3 个检查部位；撒谎时一定包含谎言对应的部位
    let parts = Object.keys(cat.parts).sort(() => Math.random() - 0.5).slice(0, 3);
    if (this.lying && !parts.includes(lie.part)) parts[randi(0, 2)] = lie.part;
    let value = this.item.base;
    this.clues = parts.map((part) => {
      if (this.lying && part === lie.part) return { part, text: lie.text, mult: 1, revealed: false, isLie: true };
      const v = pick(cat.parts[part]);
      if (v.length > 2 && v[2] === "leaky") this.item.leaky = true;
      value *= Number(v[1]);
      return { part, text: v[0], mult: Number(v[1]), revealed: false, isLie: false };
    });
    // 以“这个部位的平均结果”为基准：好线索让真实价值高于参考价，坏线索低于参考价
    for (const part of parts) value /= meanMult(cat.parts[part]);
    if (this.lying) value *= Number(lie.mult);
    this.trueValue = Math.max(10, Math.round(value * rand(0.9, 1.1)));

    const greed = rand(tuning.greed_min, tuning.greed_max) + Number(this.persona.greed_add);
    this.ask = round10(this.item.base * greed);
    let floorRatio = rand(tuning.min_price_min, tuning.min_price_max) + Number(this.persona.floor_add);
    if (this.lying) floorRatio *= tuning.liar_min_factor;
    this.minPrice = Math.min(round10(this.trueValue * floorRatio), this.ask);
    this.patience = tuning.patience_start * Number(this.persona.patience_mult);
    this.roundsLeft = tuning.haggle_rounds;
  }

  makeItem(catalog) {
    const row = pick(catalog.items);
    const cond = pickWeighted(catalog.conditions);
    return {
      name: String(cond[0]) + String(row[0]), tag: row[1],
      base: Math.max(10, Math.round(Number(row[2]) * Number(cond[1]))),
      art: catalog.categories[row[1]].art, leaky: false,
    };
  }

  line(kind) {
    const pool = this.persona[kind] || [""];
    return String(pick(pool)).replace("{ask}", String(this.ask));
  }

  reveal(i) { this.clues[i].revealed = true; return `${this.clues[i].part}：${this.clues[i].text}`; }

  /** 质疑来历。mood：caught（拿出证据揭穿）/ confess（心虚招认）/ unproven（没证据）/ honest（冤枉了老实人） */
  challenge() {
    const t = this.tuning;
    this.challengeCount++;
    if (this.lying && !this.exposed) {
      const lieSeen = this.clues.some((c) => c.isLie && c.revealed);
      const confess = this.challengeCount >= 2 && Math.random() < t.confess_chance;
      if (lieSeen || confess) {
        this.exposed = true;
        // 被揭穿就说实话：要价降到真实价值，底价再低一截，揭穿骗子一定有赚头
        this.minPrice = round10(this.trueValue * t.exposed_floor_ratio);
        this.ask = Math.max(this.minPrice, round10(this.trueValue * t.exposed_ask_ratio));
        return { text: `“${this.line("caught")}”`, mood: lieSeen ? "caught" : "confess" };
      }
      this.patience -= t.challenge_unproven_loss;
      return { text: `“${this.line("deny")}”`, mood: "unproven" };
    }
    this.patience -= t.challenge_honest_loss * this.challengeCount;
    return { text: `“${this.line("offended")}”`, mood: "honest" };
  }

  /** 出价。result：accept / counter / leave */
  offer(amount) {
    const t = this.tuning;
    if (amount >= this.minPrice) return { result: "accept", text: `“${this.line("accept")}”` };
    this.roundsLeft--;
    const gap = (this.minPrice - amount) / this.minPrice;
    this.patience -= t.patience_base_loss + t.patience_gap_loss * gap;
    if (this.patience <= 0 || this.roundsLeft <= 0) return { result: "leave", text: `“${this.line("leave")}”` };
    this.ask = Math.max(round10(Math.max(this.minPrice * t.counter_floor, (amount + this.ask) / 2)), this.minPrice);
    return { result: "counter", text: `“${this.line("counter")}”` };
  }

  profit(paid) { return this.trueValue - paid; }
}
