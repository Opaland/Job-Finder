"""Contacts recruteurs (mini-CRM par entreprise)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Contact

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    name: str
    role: str
    email: str
    phone: str
    notes: str


class ContactCreate(BaseModel):
    company: str
    name: str
    role: str = ""
    email: str = ""
    phone: str = ""
    notes: str = ""


class ContactUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


@router.get("", response_model=list[ContactOut])
def list_contacts(company: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Contact)
    if company:
        query = query.filter(Contact.company.ilike(company.strip()))
    return query.order_by(Contact.company, Contact.name).all()


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(400, "Le nom du contact est obligatoire.")
    if not payload.company.strip():
        raise HTTPException(400, "L'entreprise du contact est obligatoire.")
    contact = Contact(
        company=payload.company.strip(),
        name=payload.name.strip(),
        role=payload.role.strip(),
        email=payload.email.strip(),
        phone=payload.phone.strip(),
        notes=payload.notes,
    )
    db.add(contact)
    db.commit()
    return contact


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, payload: ContactUpdate, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contact introuvable")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and not (data["name"] or "").strip():
        raise HTTPException(400, "Le nom du contact ne peut pas être vide.")
    for field, value in data.items():
        if value is None:
            continue
        setattr(contact, field, value.strip() if field != "notes" else value)
    db.commit()
    return contact


@router.delete("/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contact introuvable")
    db.delete(contact)
    db.commit()
    return {"deleted": True}
