/**
 * Stub for the real backend. Replace with the actual API call.
 * Returns a markdown-formatted answer with [[Ch.NNN|Title]] tokens
 * that the chat renderer turns into CitationPill components.
 */
export type RobinAnswer = {
  text: string;
  citations: { chapter: number; title: string }[];
};

const MOCKS: Record<string, RobinAnswer> = {
  default: {
    text:
      "An interesting thread. Let me read what the stones remember.\n\nThe record is incomplete in places — there are silences the World Government has worked very hard to keep — but here is what is carved.\n\nIf you'd like, narrow the question and I'll pull the specific edges of the graph that bear on it.",
    citations: [],
  },
  emperors: {
    text:
      "The Four Emperors — the *Yonkō* — are the four pirates whose power is recognized as a counterweight to the Marines and the World Government in the New World.\n\nFollowing the events of Wano and the dissolution of the old order, the current four are:\n\n- **Monkey D. Luffy**, captain of the Straw Hat Pirates [[Ch.1053|The New Era]]\n- **Buggy**, figurehead of the Cross Guild [[Ch.1056|The New Emperors of the Sea]]\n- **Shanks**, captain of the Red Hair Pirates [[Ch.1054|Hand of Flame]]\n- **Marshall D. Teach**, captain of the Blackbeard Pirates [[Ch.925|Beasts Pirates' All-Stars]]\n\nKaido and Big Mom held the seats prior to their defeat in Wano [[Ch.1049|The Strongest]]. Whitebeard's seat passed long ago, at Marineford [[Ch.576|The End of the Battle]].",
    citations: [
      { chapter: 1053, title: "The New Era" },
      { chapter: 1056, title: "The New Emperors of the Sea" },
      { chapter: 1054, title: "Hand of Flame" },
      { chapter: 925, title: "Beasts Pirates' All-Stars" },
      { chapter: 1049, title: "The Strongest" },
      { chapter: 576, title: "The End of the Battle" },
    ],
  },
  void: {
    text:
      "A question close to me.\n\nMy connection to the Void Century is through Ohara — the island of scholars where I was born and where my mother, Nico Olvia, studied the Poneglyphs [[Ch.391|Ohara's Tragedy]]. I am, so far as the record shows, the only living person able to read them [[Ch.398|Sabaody Archipelago]].\n\nThe Void Century is the hundred-year gap the World Government erased from history, between roughly 800 and 900 years before the present day. The Poneglyphs are the surviving record — carved in a script the Government could not destroy [[Ch.395|Devil's Inheritance]].\n\nWhat I am still searching for is the *True History* — the account assembled from all the Road Poneglyphs that converge on Laugh Tale [[Ch.967|Roger and Whitebeard]].",
    citations: [
      { chapter: 391, title: "Ohara's Tragedy" },
      { chapter: 398, title: "Sabaody Archipelago" },
      { chapter: 395, title: "Devil's Inheritance" },
      { chapter: 967, title: "Roger and Whitebeard" },
    ],
  },
};

export async function askRobin(question: string): Promise<RobinAnswer> {
  // Simulate "reading the Poneglyphs"
  await new Promise((r) => setTimeout(r, 2400));

  const q = question.toLowerCase();
  if (q.includes("emperor") || q.includes("yonko") || q.includes("yonkō")) return MOCKS.emperors;
  if (q.includes("void") || q.includes("ohara") || q.includes("robin")) return MOCKS.void;
  return MOCKS.default;
}
