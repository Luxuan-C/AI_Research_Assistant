const USE_MOCK = true;

export async function registerUser({ name, email, password }) {
  if (!email.endsWith(".edu.au")) {
    throw new Error("Please use a valid academic email address (.edu.au)");
  }
  if (USE_MOCK) {
    return { id: "u1", name, email };
  }
  // real backend call goes here later
}

export async function loginUser({ email, password }) {
  if (USE_MOCK) {
    return { id: "u1", name: "Test User", email };
  }
  // real backend call goes here later
}