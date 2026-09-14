from sqlalchemy import text
from sqlalchemy.orm import Session

from schemas.address_schemas import AddAddressRequest, AddAddressResponse, UpdateAddressRequest

def have_default_address(user_id: int, db: Session) -> bool:
    query = text("""
        SELECT 1
        FROM addresses
        WHERE user_id = :user_id
          AND is_default = 1
          AND deleted_at IS NULL
        LIMIT 1;
    """)

    return db.execute(query, {"user_id": user_id}).scalar() is not None


def is_default_address(address_id: int, user_id: int, db: Session) -> bool:
    query = text("""
        SELECT 1
        FROM addresses
        WHERE id = :address_id
          AND user_id = :user_id
          AND is_default = 1
          AND deleted_at IS NULL
        LIMIT 1;
    """)

    return db.execute(
        query,
        {
            "address_id": address_id,
            "user_id": user_id
        }
    ).scalar() is not None

def clear_default_address(user_id: int, db: Session):
    query = text("""
        UPDATE addresses
        SET is_default = 0
        WHERE user_id = :user_id
          AND is_default = 1
          AND deleted_at IS NULL;
    """)
    db.execute(query, {"user_id": user_id})


def address_belongs_to_user(user_id: int, address_id: int, db: Session) -> bool:
    query = text("""
        SELECT 1
        FROM addresses
        WHERE id = :address_id
          AND user_id = :user_id
          AND deleted_at IS NULL
        LIMIT 1;
    """)

    return db.execute(query, {
        "address_id": address_id,
        "user_id": user_id
    }).scalar() is not None


def _mark_to_default(user_id: int, address_id: int, db: Session):
    clear_default_address(user_id, db)

    query = text("""
        UPDATE addresses
        SET is_default = 1
        WHERE id = :address_id
          AND user_id = :user_id
          AND deleted_at IS NULL;
    """)

    db.execute(query, {
        "address_id": address_id,
        "user_id": user_id
    })


def mark_to_default(user_id: int, address_id: int, db: Session):
    try:
        if not address_belongs_to_user(user_id, address_id, db):
            return 404, "Address not found"

        if is_default_address(address_id, user_id, db):
            return 200, "Address marked as default successfully."

        _mark_to_default(user_id, address_id, db)

        db.commit()

    except Exception:
        db.rollback()
        raise

    return 200, "Address marked as default successfully."


def create_address(data: AddAddressRequest, user_id: int, db: Session) -> AddAddressResponse:
    try:
        is_default = data.is_default
        if is_default or not have_default_address(user_id, db):
            clear_default_address(user_id, db)
            is_default = True

        insert_query = text("""
            INSERT INTO addresses (
                user_id,
                full_name,
                phone_number,
                alternate_phone,
                address,
                landmark,
                city,
                state,
                country,
                postal_code,
                address_type,
                delivery_instructions,
                is_default
            )
            VALUES (
                :user_id,
                :full_name,
                :phone_number,
                :alternate_phone,
                :address,
                :landmark,
                :city,
                :state,
                :country,
                :postal_code,
                :address_type,
                :delivery_instructions,
                :is_default
            )
        """)

        db.execute(insert_query, {
            "user_id": user_id,
            "full_name": data.full_name.strip(),
            "phone_number": data.phone_number,
            "alternate_phone": data.alternate_phone,
            "address": data.address.strip(),
            "landmark": data.landmark,
            "city": data.city.strip(),
            "state": data.state.strip(),
            "country": data.country,
            "postal_code": data.postal_code,
            "address_type": data.address_type.value,
            "delivery_instructions": data.delivery_instructions,
            "is_default": is_default
        })

        address_id = db.execute(
            text("SELECT LAST_INSERT_ID();")
        ).scalar()

        db.commit()

        return AddAddressResponse(
            message="Address added successfully.",
            address_id=address_id
        )

    except Exception:
        db.rollback()
        raise


def get_addresses(user_id: int, db: Session) -> list[dict]:
    query = text("""
        SELECT
            id,
            full_name,
            phone_number,
            alternate_phone,
            address,
            landmark,
            city,
            state,
            country,
            postal_code,
            address_type,
            delivery_instructions,
            is_default,
            updated_at
        FROM addresses
        WHERE user_id = :user_id
          AND deleted_at IS NULL
        ORDER BY is_default DESC, updated_at DESC;
    """)

    rows = db.execute(
        query,
        {"user_id": user_id}
    ).mappings().all()

    return [dict(row) for row in rows]


def get_address(user_id: int, address_id: int, db: Session):
    query = text("""
        SELECT
            id,
            full_name,
            phone_number,
            alternate_phone,
            address,
            landmark,
            city,
            state,
            country,
            postal_code,
            address_type,
            delivery_instructions,
            is_default,
            is_used_for_order,
            updated_at
        FROM addresses
        WHERE id = :address_id
          AND user_id = :user_id
          AND deleted_at IS NULL;
    """)

    row = db.execute(
        query,
        {
            "address_id": address_id,
            "user_id": user_id
        }
    ).mappings().first()

    if not row:
        return None

    return dict(row)

def update_address(data: UpdateAddressRequest, user_id: int, address_id: int, db: Session):
    try:
        if not address_belongs_to_user(user_id, address_id, db):
            return 404, "Address not found"
        
        if data.is_default and not is_default_address(address_id, user_id, db):
            _mark_to_default(user_id, address_id, db)

        query = text("""
            UPDATE addresses
                SET
                    full_name = :full_name,
                    phone_number = :phone_number,
                    alternate_phone = :alternate_phone,
                    address = :address,
                    landmark = :landmark,
                    city = :city,
                    state = :state,
                    country = :country,
                    postal_code = :postal_code,
                    address_type = :address_type,
                    delivery_instructions = :delivery_instructions,
                    updated_at = NOW()
                WHERE user_id = :user_id
                AND id = :address_id
                AND deleted_at IS NULL; 
        """)
        db.execute(
            query,
            {
                "user_id": user_id,
                "address_id": address_id,
                "full_name": data.full_name.strip(),
                "phone_number": data.phone_number,
                "alternate_phone": data.alternate_phone,
                "address": data.address.strip(),
                "landmark": data.landmark,
                "city": data.city.strip(),
                "state": data.state.strip(),
                "country": data.country,
                "postal_code": data.postal_code,
                "address_type": data.address_type.value,
                "delivery_instructions": data.delivery_instructions
            }
        )
        db.commit()

        return 204, "Address Update successful"
    
    except Exception:
        db.rollback()
        raise 
    

def get_first_non_default_address(user_id: int, db: Session):
    query = text("""
        SELECT id
        FROM addresses
        WHERE user_id = :user_id
          AND is_default = 0
          AND deleted_at IS NULL
        ORDER BY updated_at DESC
        LIMIT 1;
    """)

    return db.execute(
        query,
        {"user_id": user_id}
    ).scalar()


def delete_address(address_id: int, user_id: int, db: Session):
    try:
        if not address_belongs_to_user(user_id, address_id, db):
            return 404, "Address not found"

        if is_default_address(address_id, user_id, db):
            new_default_address_id = get_first_non_default_address(user_id, db)

            if new_default_address_id is not None:
                _mark_to_default(user_id, new_default_address_id, db)

        delete_query = text("""
            UPDATE addresses
            SET deleted_at = NOW()
            WHERE user_id = :user_id
              AND id = :address_id;
        """)

        db.execute(delete_query, {
            "user_id": user_id,
            "address_id": address_id
        })

        db.commit()

    except Exception:
        db.rollback()
        raise

    return 204, "Address deleted successfully."