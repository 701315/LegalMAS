// src/marketing/context/ContactModalContext.tsx

import React, { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";
import ContactModal from "../components/home/ContactModal";

interface ContactModalContextType {
  openContactModal: () => void;
}

const ContactModalContext = createContext<ContactModalContextType | undefined>(undefined);

export const ContactModalProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [contactOpen, setContactOpen] = useState(false);
  const [formEmail, setFormEmail] = useState("");
  const [formMessage, setFormMessage] = useState("");

  const handleContactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const subject = encodeURIComponent("Steloom demo request");
    const body = encodeURIComponent(`Email: ${formEmail}\n\n${formMessage}`);
    window.location.href = `mailto:vladimir.gorelov.mail@gmail.com?subject=${subject}&body=${body}`;
    setContactOpen(false);
  };

  return (
    <ContactModalContext.Provider value={{ openContactModal: () => setContactOpen(true) }}>
      {children}
      <ContactModal
        open={contactOpen}
        email={formEmail}
        message={formMessage}
        onEmailChange={setFormEmail}
        onMessageChange={setFormMessage}
        onClose={() => setContactOpen(false)}
        onSubmit={handleContactSubmit}
      />
    </ContactModalContext.Provider>
  );
};

export const useContactModal = () => {
  const context = useContext(ContactModalContext);
  if (!context) {
    throw new Error("useContactModal must be used within a ContactModalProvider");
  }
  return context;
};


