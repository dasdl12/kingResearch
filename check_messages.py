#!/usr/bin/env python
"""Quick script to check messages in database."""

from src.database.models import get_db_connection

conn = get_db_connection()
if conn:
    with conn.cursor() as cursor:
        # Check messages
        cursor.execute("""
            SELECT id, conversation_id, role, agent, 
                   LEFT(content, 50) as content_preview,
                   created_at
            FROM messages 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        messages = cursor.fetchall()
        
        print("\n=== Recent Messages ===")
        for msg in messages:
            print(f"ID: {msg['id']}")
            print(f"  Conv: {msg['conversation_id']}")
            print(f"  Role: {msg['role']}, Agent: {msg['agent']}")
            print(f"  Content: {msg['content_preview']}...")
            print(f"  Time: {msg['created_at']}")
            print()
        
        # Check conversations
        cursor.execute("""
            SELECT id, title, message_count, created_at
            FROM conversations
            ORDER BY created_at DESC
            LIMIT 5
        """)
        convs = cursor.fetchall()
        
        print("\n=== Recent Conversations ===")
        for conv in convs:
            print(f"ID: {conv['id']}")
            print(f"  Title: {conv['title']}")
            print(f"  Messages: {conv['message_count']}")
            print(f"  Created: {conv['created_at']}")
            print()
    
    conn.close()

