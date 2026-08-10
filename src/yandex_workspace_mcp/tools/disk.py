from mcp.server.fastmcp import FastMCP
from yandex_workspace_mcp.services.disk_service import DiskService
from yandex_workspace_mcp.config import Settings
import json

def register_disk_tools(mcp: FastMCP, service: DiskService, settings: Settings) -> None:
    if not settings.disk.enabled:
        return

    @mcp.tool()
    async def disk_list(path: str, limit: int = 100, offset: int = 0) -> str:
        """List contents of a directory on Yandex Disk.
        
        Args:
            path: Directory path (e.g. '/' or '/Documents')
            limit: Maximum items to return
            offset: Pagination offset
        """
        result = await service.list_folder(path, limit, offset)
        return json.dumps(result.model_dump(mode="json"), indent=2)

    @mcp.tool()
    async def disk_find(query: str, path: str = "/", limit: int = 20) -> str:
        """Find files on Yandex Disk matching a name query.
        
        Args:
            query: Substring to search for in filenames
            path: Root path to search within
            limit: Maximum results to return
        """
        result = await service.find_files(query, path, limit)
        return json.dumps([item.model_dump(mode="json") for item in result], indent=2)

    @mcp.tool()
    async def disk_get_metadata(path: str) -> str:
        """Get metadata for a specific file or folder on Yandex Disk.
        
        Args:
            path: Path to the file or folder.
        """
        result = await service.get_metadata(path)
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def disk_read(path: str) -> str:
        """Get file details and a download link for a file on Yandex Disk.
        
        Use this tool to retrieve a file. The tool returns metadata and a temporary download URL.
        You can use the URL to fetch the file contents if needed. Do not use this tool on directories.
        
        Args:
            path: Path to the file on Yandex Disk.
        """
        result = await service.read_file(path)
        return json.dumps(result, indent=2)

    # Register write tools only if enabled
    if settings.disk.write:
        @mcp.tool()
        async def disk_upload(path: str, overwrite: bool = False) -> str:
            """Get an upload URL to upload a file to Yandex Disk.
            
            This tool does not upload the file directly. Instead, it provides a URL
            that you can use to PUT the file content.
            
            Args:
                path: The destination path on Yandex Disk (e.g., '/Work/new_file.txt').
                overwrite: Whether to overwrite if the file already exists.
            """
            url = await service.get_upload_link(path, overwrite)
            return f"Upload link obtained. Use PUT request to upload data to: {url}"

        @mcp.tool()
        async def disk_create_folder(path: str) -> str:
            """Create a new folder on Yandex Disk.
            
            Args:
                path: Path for the new folder.
            """
            await service.create_folder(path)
            return f"Folder {path} created successfully."

        @mcp.tool()
        async def disk_move(from_path: str, to_path: str, overwrite: bool = False) -> str:
            """Move a file or folder on Yandex Disk.
            
            Args:
                from_path: The current path.
                to_path: The destination path.
                overwrite: Whether to overwrite the destination if it exists.
            """
            await service.move(from_path, to_path, overwrite)
            return f"Successfully moved {from_path} to {to_path}."

        @mcp.tool()
        async def disk_copy(from_path: str, to_path: str, overwrite: bool = False) -> str:
            """Copy a file or folder on Yandex Disk.
            
            Args:
                from_path: The path of the resource to copy.
                to_path: The destination path.
                overwrite: Whether to overwrite the destination if it exists.
            """
            await service.copy(from_path, to_path, overwrite)
            return f"Successfully copied {from_path} to {to_path}."

    if settings.disk.delete:
        @mcp.tool()
        async def disk_delete(path: str, permanently: bool = False) -> str:
            """Delete a file or folder on Yandex Disk.
            
            Destructive operation.
            
            Args:
                path: Path of the resource to delete.
                permanently: If true, bypasses the Trash.
            """
            await service.delete(path, permanently)
            return f"Successfully deleted {path} (permanently: {permanently})."
