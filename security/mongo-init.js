// Root создаётся entrypoint образа в admin, приложение — в security_lab.
const appDb = db.getSiblingDB("security_lab");
appDb.createUser({
  user: "lab_app",
  pwd: process.env.MONGO_APP_PASSWORD,
  roles: [{ role: "readWrite", db: "security_lab" }],
});
appDb.accounts.insertMany([
  { username: "alice", display_name: "Учебная запись Алисы" },
  { username: "bob", display_name: "Учебная запись Боба" },
]);
