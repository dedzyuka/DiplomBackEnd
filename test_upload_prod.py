import grpc
import sys
sys.path.append("app/grpcServ/app/protobuf")
import mess_pb2, mess_pb2_grpc

def test_upload():
    channel = grpc.insecure_channel("localhost:50056")
    stub = mess_pb2_grpc.AttachmentServiceStub(channel)

    # Токен получите предварительно через Login
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMmFhOTFlNy1iMzUwLTQ2NDItOWZmYy0xOTViZTU2YWQwMjYiLCJzaWQiOiJlNTNkMDIzYy04Yzk1LTQ1MGYtYmUzZC0zZDE5NzBhNzRiNTQiLCJpc3MiOiJtZXNzZW5nZXItYmFja2VuZCIsImF1ZCI6Im1lc3Nlbmdlci1jbGllbnRzIiwiaWF0IjoxNzc5Nzk4MjgxLCJuYmYiOjE3Nzk3OTgyODEsImV4cCI6MTc3OTc5OTE4MSwianRpIjoiODI1MGU2MGItODg3Yy00YzkwLWFmNzAtMzQwMDZkOWZjOWQyIiwidHlwZSI6ImFjY2VzcyJ9.2DnpLBVduaB4cw4hiVvtt0wTc-w75wDTLP89LWxSdNs"

    def gen():
        yield mess_pb2.UploadAttachmentRequest(
            metadata=mess_pb2.AttachmentInput(
                file_name="test.jpg",
                mime_type="image/jpeg"
            )
        )
        with open("test.jpg", "rb") as f:
            while chunk := f.read(1024):
                yield mess_pb2.UploadAttachmentRequest(chunk=chunk)

    metadata = [("authorization", f"Bearer {token}")]
    resp = stub.UploadAttachment(gen(), metadata=metadata)
    print(resp)

if __name__ == "__main__":
    test_upload()