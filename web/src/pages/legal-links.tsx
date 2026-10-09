import { Link } from "react-router-dom";

export const TERMS_DATE = "October 8, 2026";

export function LegalLinks() {
  return (
    <span className="legal-links">
      <Link to="/privacy">Privacy</Link> · <Link to="/terms">Terms</Link> · <Link to="/accessibility">Accessibility</Link> · <Link to="/support">Support</Link> · <Link to="/download">Downloads</Link>
    </span>
  );
}
