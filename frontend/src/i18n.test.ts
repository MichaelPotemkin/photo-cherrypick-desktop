import { describe, expect, it } from "vitest";

import { selectPlural, translate } from "./i18n";

describe("translate — English plurals", () => {
  it("uses the singular form for exactly 1", () => {
    expect(translate("en", "n_photos", { n: 1 })).toBe("1 photo");
    expect(translate("en", "sub_bursts", { n: 1 })).toBe("1 burst");
    expect(translate("en", "sub_scenes", { n: 1 })).toBe("1 scene");
  });

  it("uses the plural form for 0 and >1", () => {
    expect(translate("en", "n_photos", { n: 0 })).toBe("0 photos");
    expect(translate("en", "n_photos", { n: 2 })).toBe("2 photos");
    expect(translate("en", "sub_bursts", { n: 12 })).toBe("12 bursts");
  });
});

describe("translate — fallbacks and invariants", () => {
  it("leaves non-pluralized keys untouched", () => {
    expect(translate("en", "cancel")).toBe("Cancel");
    expect(translate("uk", "cancel")).toBe("Скасувати");
  });

  it("does not split on '|' without a numeric n var", () => {
    // The raw value contains a pipe; without `n` it must not be treated as a plural choice.
    expect(translate("en", "n_photos")).toBe("{n} photo|{n} photos");
  });

  it("treats Slavic count nouns that lack plural forms as invariant", () => {
    // uk/ru render photos as the indeclinable "фото" — no "|" form, so n is just interpolated.
    expect(translate("uk", "n_photos", { n: 1 })).toBe("1 фото");
    expect(translate("ru", "n_photos", { n: 5 })).toBe("5 фото");
  });

  it("falls back to English for a key missing in a locale", () => {
    expect(translate("uk", "app_title")).toBe("Photo Cherrypick");
  });

  it("returns the raw key when it is unknown everywhere", () => {
    expect(translate("en", "does_not_exist")).toBe("does_not_exist");
  });
});

describe("selectPlural", () => {
  it("English is two-form: 0 = other", () => {
    expect(selectPlural("en", 1)).toBe(0);
    expect(selectPlural("en", 0)).toBe(1);
    expect(selectPlural("en", 2)).toBe(1);
    expect(selectPlural("en", 21)).toBe(1);
  });

  it("East-Slavic one/few/many rule (uk, ru)", () => {
    for (const lang of ["uk", "ru"] as const) {
      expect(selectPlural(lang, 1)).toBe(0); // one
      expect(selectPlural(lang, 21)).toBe(0); // one
      expect(selectPlural(lang, 2)).toBe(1); // few
      expect(selectPlural(lang, 24)).toBe(1); // few
      expect(selectPlural(lang, 5)).toBe(2); // many
      expect(selectPlural(lang, 0)).toBe(2); // many
      expect(selectPlural(lang, 11)).toBe(2); // many (teens are an exception)
      expect(selectPlural(lang, 12)).toBe(2); // many
      expect(selectPlural(lang, 111)).toBe(2); // many
    }
  });
});
