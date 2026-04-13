import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

const allowlist = (process.env.ALLOWED_EMAILS ?? "")
  .split(",")
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [Google],
  pages: {
    signIn: "/signin",
  },
  callbacks: {
    signIn({ profile }) {
      const email = profile?.email?.toLowerCase();
      if (!email) return false;
      if (allowlist.length === 0) return false;
      return allowlist.includes(email);
    },
    authorized({ auth, request }) {
      const { pathname } = request.nextUrl;
      if (pathname.startsWith("/signin")) return true;
      if (pathname.startsWith("/api/auth")) return true;
      return !!auth?.user?.email;
    },
    session({ session }) {
      return session;
    },
  },
});
